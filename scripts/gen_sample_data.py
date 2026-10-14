"""샘플 데이터 생성기: 2026년 7~9월 매주 일요일 경기를 실제 API로 돌려 DB를 채운다.

왜 API로 돌리나: 기록·통계·Rating 이력·Pair·타이틀·Insight·기사가 서로 맞물려야 해서
INSERT문을 손으로 쓰면 정합성이 깨진다. 실제 서비스 로직을 그대로 태우고, 시계만 과거로 돌린다.

사용법(빈 DB, alembic upgrade head 직후, 개발용 패키지 time-machine 필요):
    pip install time-machine
    python -m scripts.gen_sample_data          # .env의 DATABASE_URL 대상
그 다음 mysqldump로 데이터만 뽑아 INSERT문을 만든다(README 참고).

- 선수 23명: ROSTER의 값을 시작 Rating(MEMBER.INITIAL_RATING)으로 등록
- 일정 13회(7/5 ~ 9/27 일요일), 3팀, 15~21명, 하루 7~9경기(10분), 가끔 게스트 1~2명·지각 합류
- 대진은 밀어내기(이긴 팀 잔류, 최대 2연속, 무승부면 오래 뛴 팀이 빠짐)를 관리자가 매번 지정
- 득점/도움/자책골/게스트 골/골 취소(입력 정정) 포함, 일정확정→프리뷰 기사, 일정마감→MVP·마감 기사
- 기사는 OpenAI 대신 이 파일의 SampleArticleWriter(템플릿)가 Insight 사실로 작성
"""
from __future__ import annotations

import math
import os
import random
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from typing import Any

os.environ["ARTICLE_GENERATION_SYNC"] = "true"
os.environ["AI_PROVIDER"] = "stub"
os.environ["ENABLE_BACKGROUND_JOBS"] = "false"

import time_machine  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import text  # noqa: E402

import app.wire.article_service as article_service  # noqa: E402
from app.core.database import SessionLocal, engine  # noqa: E402
from app.core.security import login_limiter  # noqa: E402
from app.integrations.openai.writer import validate_draft  # noqa: E402
from app.main import app  # noqa: E402
from app.services import club_service  # noqa: E402
from app.services.match_service import auto_end_due_matches  # noqa: E402

KST = timezone(timedelta(hours=9))
SEED = 20260705
CLUB_SLUG, CLUB_NAME, PIN = "sanha", "YPR", "7777"

# 순위, 이름, 시작 Rating (7월 시작값)
ROSTER = [
    ("손원일", 1081), ("김응철", 1078), ("안휘진", 1078), ("유창우", 1075), ("전원재", 1060), ("김현섭", 1054),
    ("윤기창", 1054), ("이종훈", 1048), ("김상균", 1024), ("박영현", 1015), ("이용준", 1006), ("변현우", 997),
    ("김재홍", 991), ("김동근", 979), ("이민선", 973), ("권태홍", 970), ("진선호", 967), ("임우철", 952),
    ("이채현", 928), ("김승준", 922), ("윤영문", 922), ("구대현", 916), ("김병채", 910),
]
ROLE_WEIGHT = {  # 득점, 도움 가중치
    "FW": (1.8, 1.0), "MF": (1.2, 1.5), "DF": (0.6, 0.8), "GK": (0.15, 0.4),
}
CANCEL_MEMOS = ("중복 입력", "득점자 정정")


def sundays(start: date, end: date) -> list[date]:
    d = start + timedelta(days=(6 - start.weekday()) % 7)
    out = []
    while d <= end:
        out.append(d)
        d += timedelta(days=7)
    return out


def at(d: date, hh: int, mm: int = 0, ss: int = 0) -> datetime:
    return datetime(d.year, d.month, d.day, hh, mm, ss, tzinfo=KST)


# ---------------------------------------------------------------------- 기사(템플릿)
def _batchim(word: str) -> int | None:
    """마지막 글자 받침 코드(0=없음). 한글이 아니면 숫자/영문 발음으로 추정."""
    ch = word.strip()[-1:] or " "
    if "가" <= ch <= "힣":
        return (ord(ch) - 0xAC00) % 28
    if ch.isdigit():
        return {"0": 21, "1": 8, "3": 16, "6": 1, "7": 8, "8": 8}.get(ch, 0)
    return 4 if ch.upper() in "LMNR" else 0


def j(word: str, with_batchim: str, without: str) -> str:
    """조사: j('손원일','이','가') → '손원일이'."""
    b = _batchim(word)
    if with_batchim == "으로":
        return word + ("으로" if b and b != 8 else "로")
    return word + (with_batchim if b else without)


def josa_only(word: str, with_batchim: str, without: str) -> str:
    return j(word, with_batchim, without)[len(word):]


def tagged_list(items: list[tuple[str, str]]) -> tuple[str, str]:
    """[("이민선","11주"),("김응철","9주")] → ("이민선(11주)과 김응철(9주)", "김응철") — 조사는 마지막 이름 기준."""
    parts = [f"{n}({x})" for n, x in items]
    if len(parts) == 1:
        return parts[0], items[0][0]
    text_ = ", ".join(parts[:-1]) + josa_only(items[-2][0], "과", "와") + " " + parts[-1]
    return text_, items[-1][0]


def names_ko(names: list[str]) -> str:
    return ", ".join(names[:-1]) + (f"와 {names[-1]}" if not _batchim(names[-2]) else f"과 {names[-1]}") if len(names) > 1 else (names[0] if names else "")


_RECENT_HEADS: dict[str, list[tuple[str, str]]] = {}  # 기사 종류별 최근 제목 (유형, 선수) — 같은 유형 반복 방지
_HEAD_BONUS = {"HAT_TRICK": 14, "COMEBACK_WIN": 14, "UPSET_WIN": 12, "LATE_WINNER": 8, "RETURN_PLAYER_RESULT": 10,
               "RETURN_PLAYER": 12, "RARE_PAIR": 6, "WIN_STREAK": 4, "TITLE_AWARDED": 2,
               "CLOSE_MATCH_EXPECTED": -8, "MILESTONE_EXPECTED": -10, "MILESTONE_ACHIEVED": -4}
_METRIC = {"games": ("경기 출전", "경기"), "goals": ("골", "골"), "assists": ("도움", "개")}


def _milestone(metric: str, ms: int) -> str:
    word, _ = _METRIC.get(metric, ("골", "골"))
    return f"통산 {ms}{word}" if metric != "games" else f"통산 {ms}경기 출전"


class SampleArticleWriter:
    """Insight 사실만으로 쓰는 샘플 기사(사실 밖 내용은 쓰지 않는다). 같은 유형 사실은 한 문장으로 묶는다."""

    provider = "sample"

    def __init__(self, rng: random.Random):
        self.rng = rng

    @staticmethod
    def _name(ins: dict[str, Any]) -> str:
        f = ins.get("facts") or {}
        return (ins.get("subject") or {}).get("name") or (f.get("member") or {}).get("name") or ""

    def _group_key(self, ins: dict[str, Any], phase: str) -> tuple:
        t, f = ins["type"], ins.get("facts") or {}
        if t in ("WIN_STREAK", "SCORING_STREAK"):
            return (t, phase)
        if t == "MILESTONE_ACHIEVED":
            return (t, f.get("metric"), f.get("milestone"))
        if t == "MILESTONE_EXPECTED":
            return (t, f.get("metric"), f.get("milestone"), f.get("remaining"))
        if t == "FIRST_APPEARANCE":
            return (t,)
        if t == "TITLE_AWARDED":
            return (t, f.get("titleName"), f.get("value"))
        return (t, ins["id"])  # 묶지 않음

    def _sentence(self, t: str, phase: str, items: list[dict[str, Any]]) -> tuple[str | None, str | None]:
        """같은 그룹 Insight 묶음 → (제목 후보, 문장)."""
        f = items[0].get("facts") or {}
        names = [self._name(i) for i in items if self._name(i)]
        who = names_ko(names) if names else ""
        lead = names[0] if names else ""
        many = len(names) > 1
        head_who = f"{lead} 등 {len(names)}명" if many else lead
        g = f.get("gameNo")
        try:
            if t in ("WIN_STREAK", "SCORING_STREAK") and len({(i.get("facts") or {}).get("streak") for i in items}) > 1:
                ranked = sorted(items, key=lambda i: -(i.get("facts") or {}).get("streak", 0))
                unit = "연승" if t == "WIN_STREAK" else "주"
                tagged = [(self._name(i), f"{i['facts']['streak']}{unit}") for i in ranked if self._name(i)]
                body_, last = tagged_list(tagged)
                top, top_s = tagged[0][0], ranked[0]["facts"]["streak"]
                if t == "WIN_STREAK":
                    verb = "연승 행진을 이어가고 있다" if phase == "PRE" else "연승 행진을 이어갔다"
                    head = f"{top}, {top_s}연승" + (" 이어갈까" if phase == "PRE" else " 질주")
                else:
                    verb = "연속 득점 행진을 이어가고 있다" if phase == "PRE" else "연속 골 행진을 이어갔다"
                    head = f"{top}, {top_s}주 연속 " + ("득점 중" if phase == "PRE" else "골")
                return head, f"{body_}{josa_only(last, '이', '가')} {verb}."
            if t == "WIN_STREAK":
                s = f["streak"]
                if phase == "PRE":
                    return (f"{head_who}, {s}연승 이어갈까",
                            f"{j(who, '은', '는')} 나란히 {s}연승을 달리고 있다." if many else
                            f"{j(who, '은', '는')} {s}연승을 달리고 있다. 오늘도 승리를 이어갈지 관심이 모인다.")
                return (f"{head_who}, {s}연승 질주",
                        f"{j(who, '은', '는')} {'나란히 ' if many else ''}{s}연승을 이어갔다.")
            if t == "SCORING_STREAK":
                s = f["streak"]
                if phase == "PRE":
                    return (f"{head_who}, {s}주 연속 득점 중",
                            f"{j(who, '은', '는')} {'나란히 ' if many else ''}{s}주 연속으로 골 맛을 보고 있다.")
                return (f"{head_who}, {s}주 연속 골",
                        f"{j(who, '은', '는')} {'나란히 ' if many else ''}{s}주 연속 골 행진을 이어갔다.")
            if t == "MILESTONE_ACHIEVED":
                ph = _milestone(f["metric"], f["milestone"])
                if f["metric"] == "games" and phase == "POST" and len(names) > 4:
                    return None, f"{lead} 등 {len(names)}명이 {ph} 고지를 밟았다."
                return f"{head_who}, {ph} 달성", f"{j(who, '이', '가')} {'나란히 ' if many else ''}{ph} 고지를 밟았다."
            if t == "MILESTONE_EXPECTED":
                ph = _milestone(f["metric"], f["milestone"])
                unit = _METRIC.get(f["metric"], ("", "골"))[1]
                return (f"{head_who}, {ph}까지 {f['remaining']}{unit}",
                        f"{j(who, '은', '는')} {ph}까지 {f['remaining']}{unit}만 남겨 두었다.")
            if t == "FIRST_APPEARANCE":
                if len(names) > 3:
                    return None, None
                return None, f"{j(who, '은', '는')} 오늘이 기록 집계 후 첫 출전이다."
            if t == "RETURN_PLAYER":
                d = f["daysSinceLastAppearance"]
                return f"{lead}, {d}일 만의 복귀", f"{j(lead, '이', '가')} {d}일 만에 다시 그라운드를 밟는다."
            if t == "RETURN_PLAYER_RESULT":
                d, goals, wins, games = f["daysSinceLastAppearance"], f.get("goalsToday", 0), f.get("winsToday", 0), f.get("gamesToday")
                tail = (f"{goals}골 {wins}승을 보탰다" if goals and wins else f"{goals}골을 기록했다" if goals
                        else f"골은 없었지만 {wins}승을 챙겼다" if wins else "다시 손발을 맞췄다")
                return (f"{lead}, {d}일 만의 복귀전서 {goals}골" if goals else f"{lead}, {d}일 만의 복귀전",
                        f"{d}일 만에 돌아온 {j(lead, '은', '는')} {games}경기에 나서 {tail}." if games else
                        f"{d}일 만에 돌아온 {j(lead, '은', '는')} {tail}.")
            if t == "RARE_PAIR":
                ms = [m.get("name") for m in f.get("members", []) if m.get("name")]
                if len(ms) < 2:
                    return None, None
                pair = f"{ms[0]}·{ms[1]}"
                if f.get("neverSameTeam"):
                    return f"{pair}, 처음으로 한 팀", f"{j(names_ko(ms), '이', '가')} 처음으로 같은 팀에서 호흡을 맞춘다."
                n = f.get("sessionsSinceLastSameTeam")
                return f"{pair}, {n}주 만에 한 팀", f"{j(names_ko(ms), '은', '는')} {n}번의 일정 만에 다시 같은 팀이 됐다."
            if t == "CLOSE_MATCH_EXPECTED":
                return "오늘은 접전 예고", "팀 간 전력이 고르게 나뉘어 어느 팀도 쉽게 승리를 장담하기 어렵다."
            if t == "LATE_WINNER":
                sec = f["remainingSec"]
                return (f"{lead}, 종료 {sec}초 전 결승골",
                        f"{g}경기는 {lead}의 발끝에서 갈렸다. 종료 {sec}초를 남기고 터진 결승골이었다.")
            if t == "COMEBACK_WIN":
                team, dd = f["winnerTeam"], f["maxDeficit"]
                return f"{team}팀, {dd}골 차 뒤집었다", f"{team}팀은 {g}경기에서 {dd}골 차로 끌려가다 경기를 뒤집었다."
            if t == "UPSET_WIN":
                team = f["winnerTeam"]
                return f"{team}팀의 반란", f"{g}경기에서는 {j(team + '팀', '이', '가')} 열세라는 예상을 깨고 승리를 가져갔다."
            if t == "HAT_TRICK":
                n = f["goals"]
                return (f"{lead}, {g}경기 해트트릭" if n == 3 else f"{lead}, 한 경기 {n}골 폭발",
                        f"{g}경기에서 {j(lead, '이', '가')} 혼자 {n}골을 몰아쳤다.")
            if t == "TITLE_AWARDED":
                tn = f["titleName"]
                unit = {"assists": "도움", "wins": "승"}.get(f.get("metric"), "골")
                val = f"({f['value']}{unit})" if f.get("value") else ""
                return (f"{head_who}, {tn}",
                        f"{j(who, '이', '가')} {'나란히 ' if many else ''}{tn}{val}에 이름을 올렸다.")
        except (KeyError, TypeError, IndexError):
            return None, None
        return None, None

    def write(self, payload: dict[str, Any], model: str):
        kind = payload.get("articleType")
        d = date.fromisoformat(payload["sessionDate"])
        md = f"{d.month}월 {d.day}일"
        club = payload.get("clubName") or ""
        phase = "PRE" if kind == "PRE_MATCH" else "POST"
        insights = sorted(payload.get("insights", []), key=lambda i: (-i["importance"], i["id"]))
        recent = _RECENT_HEADS.setdefault(kind or "", [])
        first_count = sum(1 for i in insights if i["type"] == "FIRST_APPEARANCE")

        groups: dict[tuple, list[dict[str, Any]]] = {}
        for ins in insights:
            groups.setdefault(self._group_key(ins, phase), []).append(ins)
        lines: list[str] = []
        used: list[int] = []
        heads: list[tuple] = []  # (점수, 제목, 유형, 선수, 문장, 원래 중요도)
        for key, items in groups.items():  # 삽입 순서 = 중요도 순
            t = key[0]
            head, line = self._sentence(t, phase, items)
            if not line:
                continue
            lines.append(line)
            used.extend(i["id"] for i in items)
            if head:
                who = self._name(items[0])
                score = max(i["importance"] for i in items) + _HEAD_BONUS.get(t, 0)
                if (items[0].get("facts") or {}).get("metric") == "games":
                    score -= 12  # 출전 경기 수 기록은 제목감이 약함
                if any(rt == t for rt, _ in recent[-2:]):
                    score -= 30
                if who and any(rw == who for _, rw in recent[-2:]):
                    score -= 15
                heads.append((score, head, t, who, line, max(i["importance"] for i in items)))
            if len(lines) >= 6:
                break
        heads.sort(key=lambda x: -x[0])
        if heads:  # 고른 유형 안에서는 사실 자체가 가장 큰 것을 제목으로
            best_t = heads[0][2]
            heads.sort(key=lambda x: (x[2] != best_t, -x[5] if x[2] == best_t else -x[0]))
        if heads:  # 제목이 된 사실을 본문 첫 문장·요약으로
            lines.remove(heads[0][4])
            lines.insert(0, heads[0][4])

        paras: list[str] = []
        if kind == "PRE_MATCH":
            teams = payload.get("teams") or []
            total = sum(len(t["members"]) + t.get("guestCount", 0) for t in teams)
            guests = sum(t.get("guestCount", 0) for t in teams)
            lead = f"{md} 일요일, {club} {total}명이 {len(teams)}개 팀으로 나뉘어 맞붙는다."
            if guests:
                lead += f" 게스트 {guests}명도 함께 뛴다."
            if first_count > 3:
                lead += " 오늘부터 모든 경기 기록이 쌓이기 시작한다."
            paras.append(lead)
            roster = [f"{t['teamCode']}팀은 {', '.join(t['members'][:3])} 등 {len(t['members']) + t.get('guestCount', 0)}명"
                      for t in teams]
            if roster:
                paras.append(", ".join(roster) + "으로 꾸려졌다.")
            title = heads[0][1] if heads else (f"{md}, YPR 기록의 첫 페이지" if first_count > 3 else f"{md} 일요 경기 프리뷰")
            summary = lines[0] if lines else lead
            closing = self.rng.choice(("경기 결과와 오늘의 주인공은 마감 기사에서 전한다.",
                                       "첫 경기 휘슬과 함께 오늘의 이야기가 시작된다.",
                                       "누가 오늘의 주인공이 될지는 마감 기사에서 확인할 수 있다."))
        else:
            s = payload.get("sessionSummary") or {}
            matches = s.get("matches", [])
            goals = sum(m["scoreA"] + m["scoreB"] for m in matches)
            recs = s.get("teamRecords") or {}
            best = sorted(recs.items(), key=lambda kv: (-kv[1]["wins"], kv[1]["losses"], kv[0]))
            lead = f"{md} {j(club, '은', '는')} {len(matches)}경기를 치르며 총 {goals}골을 기록했다."
            if best:
                code, r = best[0]
                lead += f" {code}팀이 {r['wins']}승 {r['draws']}무 {r['losses']}패로 가장 많은 승리를 챙겼다."
            paras.append(lead)
            scorers = s.get("topScorers") or []
            if scorers:
                top = [f"{x['name']}({x['goals']}골)" for x in scorers[:3]]
                paras.append(f"득점 순위에서는 {', '.join(top)} 순으로 앞섰다.")
            title = heads[0][1] if heads else (f"{md} 결산: {best[0][0]}팀 {best[0][1]['wins']}승" if best else f"{md} 경기 결산")
            summary = lines[0] if lines else lead
            closing = "\n".join(f"{m['gameNo']}경기  {m['teamA']} {m['scoreA']} : {m['scoreB']} {m['teamB']}" for m in matches)
        if heads:
            recent.append((heads[0][2], heads[0][3]))
        for i in range(0, len(lines), 2):
            paras.append(" ".join(lines[i:i + 2]))
        if closing:
            paras.append(closing)
        raw = {"title": title[:120], "summary": summary[:300], "body": "\n\n".join(paras), "usedInsightIds": used}
        return validate_draft(raw, payload), raw


# ---------------------------------------------------------------------- 시뮬레이션
class Sim:
    def __init__(self, client: TestClient, traveller):
        self.c, self.t = client, traveller
        self.rng = random.Random(SEED)
        self.token = ""
        self.ids: dict[str, int] = {}
        self.players: dict[int, dict[str, Any]] = {}

    # --- HTTP
    def url(self, p: str) -> str:
        return f"/api/clubs/{CLUB_SLUG}{p}"

    def call(self, method: str, path: str, body: dict | None = None, ok=(200, 201), **kw):
        r = self.c.request(method, self.url(path), json=body, headers={"Authorization": f"Bearer {self.token}"}, **kw)
        if r.status_code not in ok:
            raise RuntimeError(f"{method} {path} → {r.status_code} {r.text}")
        return r.json()

    def now(self, dt: datetime) -> None:
        self.t.move_to(dt)

    def login(self) -> None:
        login_limiter.reset()
        self.token = self.call("POST", "/admin/auth", {"password": PIN})["accessToken"]

    # --- 준비
    def setup(self) -> None:
        self.now(at(date(2026, 6, 28), 21))
        with SessionLocal() as db:
            club_service.create_club(db, CLUB_SLUG, CLUB_NAME, PIN)
        self.login()
        roles = ["FW"] * 6 + ["MF"] * 9 + ["DF"] * 6 + ["GK"] * 2
        self.rng.shuffle(roles)
        for i, (name, rating) in enumerate(ROSTER):
            joined = date(2023, 3, 1) + timedelta(days=self.rng.randrange(0, 1100))
            m = self.call("POST", "/members", {"name": name, "initialRating": rating, "joinedAt": joined.isoformat()})
            mid = m["memberId"]
            self.ids[name] = mid
            slope = self.rng.gauss(0, 1.6)
            self.players[mid] = {
                "name": name, "base": float(rating), "role": roles[i],
                "slope": slope, "attend": self.rng.uniform(0.62, 0.95), "away": set(),
            }
        # 휴가·부상: 몇 명은 여름에 연속 불참(30일 넘게 쉬면 복귀 Insight)
        for mid, weeks in zip(self.rng.sample(list(self.players), 5), (5, 5, 4, 2, 3)):
            start = self.rng.randrange(2, 7)
            self.players[mid]["away"] = set(range(start, start + weeks))
        # 상승세/하락세 몇 명
        for mid in self.rng.sample(list(self.players), 3):
            self.players[mid]["slope"] = self.rng.uniform(3.0, 4.5)
        for mid in self.rng.sample([m for m in self.players if self.players[m]["slope"] < 3], 2):
            self.players[mid]["slope"] = -self.rng.uniform(2.5, 3.5)

    def skill(self, mid: int, week: int) -> float:
        p = self.players[mid]
        return p["base"] + p["slope"] * week

    # --- 하루
    def play_day(self, week: int, d: date, last: bool) -> None:
        rng = self.rng
        # 목요일 밤: 일정 생성
        self.now(at(d - timedelta(days=3), 21, rng.randrange(0, 50)))
        self.login()
        sid = self.call("POST", "/sessions", {"sessionDate": d.isoformat(), "title": "일요 정기 경기"})["sessionId"]

        # 토요일 밤: 참석 체크
        self.now(at(d - timedelta(days=1), 21, rng.randrange(0, 50)))
        self.login()
        attend = [m for m, p in self.players.items() if week not in p["away"] and rng.random() < p["attend"]]
        pool = [m for m, p in self.players.items() if week not in p["away"] and m not in attend]
        target = rng.randint(15, 21)
        rng.shuffle(pool)
        while len(attend) < target and pool:
            attend.append(pool.pop())
        while len(attend) > target:
            attend.remove(rng.choice(attend))
        late_pool = [m for m in pool if m not in attend]
        self.call("POST", f"/sessions/{sid}/members", {"memberIds": attend})
        guests = rng.choice((0, 0, 0, 1, 1, 2)) if len(attend) < 20 else 0
        if guests:
            self.call("POST", f"/sessions/{sid}/guests", {"count": guests})

        # 일요일 07:40 팀 편성 → 일정확정(프리뷰 기사) → 게시
        self.now(at(d, 7, 40))
        self.login()
        gen = self.call("POST", f"/sessions/{sid}/teams/generate", {"teamCount": 3, "seed": rng.randrange(1, 10**9)})
        conf = self.call("POST", f"/sessions/{sid}/teams/confirm", {"generationId": gen["generationId"]})
        teams = {t["teamCode"]: t["sessionTeamId"] for t in conf["teams"]}
        self.now(at(d, 7, 46))
        self._publish_all(sid)

        # 경기: 08:00부터, 밀어내기 대진
        n_games = rng.randint(7, 9)
        late_game = rng.randint(2, 4) if late_pool and rng.random() < 0.3 else None
        clock = at(d, 8, 0)
        codes = list(teams)
        on = [codes[0], codes[1]]
        waiting = codes[2]
        consecutive = {codes[0]: 1, codes[1]: 1, codes[2]: 0}
        perf: dict[int, dict[str, float]] = defaultdict(lambda: defaultdict(float))
        for g in range(1, n_games + 1):
            if late_game == g:  # 지각 합류: 인원이 가장 적은 팀으로
                self.now(clock - timedelta(minutes=1))
                late = late_pool[0]
                detail = self.call("GET", f"/sessions/{sid}")
                small = min(detail["teams"], key=lambda t: t["headcount"])
                self.call("POST", f"/sessions/{sid}/teams/assignments",
                          {"action": "ADD", "memberId": late, "toTeamId": small["sessionTeamId"], "reason": "지각 합류"})
            self.now(clock)
            m = self.call("POST", f"/sessions/{sid}/matches/next", {"teamAId": teams[on[0]], "teamBId": teams[on[1]]})
            mid = m["matchId"]
            start = clock + timedelta(seconds=40)
            self.now(start)
            self.call("POST", f"/matches/{mid}/start")
            md = self.call("GET", f"/matches/{mid}")
            side = {"A": md["teamA"], "B": md["teamB"]}
            score = self._goals(mid, week, start, side, perf)
            # 시간 종료 → 자동 종료 → 확정
            self.now(start + timedelta(seconds=602))
            auto_end_due_matches()
            self.now(start + timedelta(seconds=660))
            self.call("POST", f"/matches/{mid}/finalize")
            win = "A" if score["A"] > score["B"] else "B" if score["B"] > score["A"] else None
            for k in ("A", "B"):
                for x in side[k]["members"]:
                    perf[x["memberId"]]["games"] += 1
                    if win == k:
                        perf[x["memberId"]]["wins"] += 1
            # 다음 대진(밀어내기): 이긴 팀 잔류(최대 2연속), 무승부면 오래 뛴 팀이 빠짐
            a, b = on
            if win:
                stay = a if win == "A" else b
                if consecutive[stay] >= 2:
                    stay = b if stay == a else a
            else:
                stay = b if consecutive[a] >= consecutive[b] else a
            out = b if stay == a else a
            consecutive[stay] += 1
            consecutive[out] = 0
            consecutive[waiting] = 1
            on, waiting = [stay, waiting], out
            clock = start + timedelta(minutes=rng.randint(13, 15))

        # 마감: MVP 수동 수여 → [일정마감](자동 타이틀·마감 기사) → 게시(마지막 주는 검토 대기로 둠)
        end = clock + timedelta(minutes=10)
        self.now(end)
        self.login()
        mvp = max(perf, key=lambda x: (perf[x]["goals"] * 3 + perf[x]["assists"] * 2 + perf[x]["wins"] * 1.5
                                        + rng.random()))
        self.call("POST", "/titles/awards", {"titleCode": "MVP", "memberId": mvp, "sessionId": sid})
        self.now(end + timedelta(minutes=2))
        self.call("POST", f"/sessions/{sid}/close")
        if not last:
            self.now(end + timedelta(minutes=25))
            self._publish_all(sid)

    def _goals(self, mid: int, week: int, start: datetime, side: dict, perf) -> dict[str, int]:
        rng = self.rng

        def strength(t: dict) -> float:
            vals = [self.skill(x["memberId"], week) + rng.gauss(0, 12) for x in t["members"]]
            vals += [960.0] * t.get("guestCount", 0)
            return sum(vals) / len(vals)

        diff = strength(side["A"]) - strength(side["B"])
        lam = {"A": 1.35 * math.exp(diff / 170), "B": 1.35 * math.exp(-diff / 170)}
        events = []
        for k in ("A", "B"):
            for _ in range(min(6, _poisson(rng, lam[k]))):
                events.append((rng.randint(15, 590), k))
        events.sort()
        score = {"A": 0, "B": 0}
        cancel_at = rng.randrange(len(events)) if events and rng.random() < 0.08 else None
        for n, (sec, k) in enumerate(events):
            opp = "B" if k == "A" else "A"
            team, members = side[k], [x["memberId"] for x in side[k]["members"]]
            body: dict[str, Any] = {"teamId": team["sessionTeamId"], "elapsedSec": sec}
            roll = rng.random()
            if roll < 0.03 and side[opp]["members"]:  # 자책골
                og = self._pick([x["memberId"] for x in side[opp]["members"]], week, "own")
                body.update(scorerMemberId=og, ownGoal=True)
            elif roll < 0.03 + 0.07 * team.get("guestCount", 0):  # 게스트 골
                body.update(guestGoal=True)
            else:
                scorer = self._pick(members, week, "goal", perf)
                body["scorerMemberId"] = scorer
                perf[scorer]["goals"] += 1
                if rng.random() < 0.62 and len(members) > 1:
                    assist = self._pick([x for x in members if x != scorer], week, "assist", perf)
                    body["assistMemberId"] = assist
                    perf[assist]["assists"] += 1
            self.now(start + timedelta(seconds=sec + rng.randint(2, 8)))
            if n == cancel_at:  # 입력 실수 → 취소(사유 기록) 후 다시 입력
                memo = rng.choice(CANCEL_MEMOS)
                wrong = dict(body)
                if memo == "득점자 정정" and body.get("scorerMemberId") and not body.get("ownGoal") and len(members) > 1:
                    wrong["scorerMemberId"] = rng.choice([x for x in members if x != body["scorerMemberId"]])
                    wrong.pop("assistMemberId", None)
                    if wrong.get("assistMemberId") == wrong["scorerMemberId"]:
                        wrong.pop("assistMemberId")
                ev = self.call("POST", f"/matches/{mid}/goals", wrong)
                self.now(start + timedelta(seconds=sec + rng.randint(15, 30)))
                self.call("POST", f"/matches/{mid}/events/{ev['eventId']}/cancel", {"memo": memo})
                if memo == "중복 입력":
                    self.call("POST", f"/matches/{mid}/goals", {**body, "idempotencyKey": f"m{mid}-g{n}"})
                    score[k] += 1
                    continue
            self.call("POST", f"/matches/{mid}/goals", {**body, "idempotencyKey": f"m{mid}-g{n}"})
            score[k] += 1
        return score

    def _pick(self, ids: list[int], week: int, kind: str, perf=None) -> int:
        idx = 0 if kind == "goal" else 1
        w = []
        for mid in ids:
            p = self.players[mid]
            base = ROLE_WEIGHT[p["role"]][idx] if kind != "own" else (1.6 if p["role"] in ("DF", "GK") else 0.5)
            today = perf[mid]["goals" if kind == "goal" else "assists"] if perf is not None else 0
            w.append(max(0.05, base * (1 + (self.skill(mid, week) - 1000) / 250) * (0.8 ** today)))
        return self.rng.choices(ids, weights=w)[0]

    def _publish_all(self, sid: int) -> None:
        for a in self.call("GET", "/articles", params={"all": "true", "sessionId": sid}):
            if a["status"] == "GENERATED":
                self.call("POST", f"/articles/{a['articleId']}/publish")


def _poisson(rng: random.Random, lam: float) -> int:
    l, k, p = math.exp(-lam), 0, 1.0
    while True:
        p *= rng.random()
        if p <= l:
            return k
        k += 1


def main() -> None:
    with engine.connect() as conn:
        if conn.execute(text("SELECT COUNT(*) FROM CLUB")).scalar():
            raise SystemExit("CLUB 테이블이 비어 있지 않습니다. 빈 DB에서 실행하세요(alembic upgrade head 직후).")
    days = sundays(date(2026, 7, 1), date(2026, 9, 30))
    with time_machine.travel(at(date(2026, 6, 28), 21), tick=False) as traveller, TestClient(app) as client:
        sim = Sim(client, traveller)
        writer = SampleArticleWriter(random.Random(SEED + 1))  # 기사 문구용 난수는 경기 난수와 분리
        article_service.get_writer = lambda: writer
        sim.setup()
        for week, d in enumerate(days):
            sim.play_day(week, d, last=(week == len(days) - 1))
            print(f"{d} 완료")
    with engine.begin() as conn:  # 기사 작성기 표기(OpenAI가 아닌 샘플 템플릿)
        conn.execute(text("UPDATE AI_ARTICLE SET MODEL_NAME = 'sample-template'"))
    print("done:", len(days), "sessions")


if __name__ == "__main__":
    main()
