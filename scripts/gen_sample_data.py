"""샘플 데이터 생성기: 2026년 7/4 ~ 10/17 매주 토요일 경기를 실제 API로 돌려 DB를 채운다.

왜 API로 돌리나: 기록·통계·Rating 이력·Pair·타이틀·Insight·기사가 서로 맞물려야 해서
INSERT문을 손으로 쓰면 정합성이 깨진다. 실제 서비스 로직을 그대로 태우고, 시계만 과거로 돌린다.

사용법(빈 DB, alembic upgrade head 직후, 개발용 패키지 time-machine 필요):
    pip install time-machine
    python -m scripts.gen_sample_data          # .env의 DATABASE_URL 대상
그 다음 mysqldump로 데이터만 뽑아 INSERT문을 만든다(README 참고).

- 선수 23명: ROSTER의 값을 시작 Rating(MEMBER.INITIAL_RATING)으로 등록
- 일정 16회(7/4 ~ 10/17 토요일), 3팀, 15~21명, 하루 7~9경기(10분), 가끔 게스트 1~2명·지각 합류
- 대진은 밀어내기(이긴 팀 잔류, 최대 2연속, 무승부면 오래 뛴 팀이 빠짐)를 관리자가 매번 지정
- 득점/도움/자책골/게스트 골/골 취소(입력 정정) 포함, 일정확정→프리뷰 기사, 일정마감→자동 타이틀·마감 기사
- 월이 바뀌면(1일 00:10) 월 마감 → 이달의 MVP 타이틀 + 발표 기사(7 · 8 · 9월). 10월은 후보 진행 중으로 끝남
- 마지막 일정(10/17)의 마감 기사는 검토 대기로 둔다. 예정 일정은 만들지 않는다
- 기사는 OpenAI 대신 기본형 기사 작성기(app/integrations/openai/template_writer.py)가 Insight 사실로 작성
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
from app.integrations.openai.template_writer import TemplateArticleWriter  # noqa: E402
from app.main import app  # noqa: E402
from app.services import club_service, mvp_service  # noqa: E402
from app.services.common import get_club_by_slug  # noqa: E402
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


def weekly(start: date, end: date, weekday: int = 5) -> list[date]:
    """start~end 사이 매주 같은 요일(기본 5 = 토요일)."""
    d = start + timedelta(days=(weekday - start.weekday()) % 7)
    out = []
    while d <= end:
        out.append(d)
        d += timedelta(days=7)
    return out


def at(d: date, hh: int, mm: int = 0, ss: int = 0) -> datetime:
    return datetime(d.year, d.month, d.day, hh, mm, ss, tzinfo=KST)


# ---------------------------------------------------------------------- 시뮬레이션
class Sim:
    def __init__(self, client: TestClient, traveller):
        self.c, self.t = client, traveller
        self.rng = random.Random(SEED)
        self.token = ""
        self.ids: dict[str, int] = {}
        self.players: dict[int, dict[str, Any]] = {}
        self.month_mark: date | None = None  # 마지막으로 월 마감을 확인한 달(1일)

    # --- HTTP
    def url(self, p: str) -> str:
        return f"/api/clubs/{CLUB_SLUG}{p}"

    def call(self, method: str, path: str, body: dict | None = None, ok=(200, 201), **kw):
        r = self.c.request(method, self.url(path), json=body, headers={"Authorization": f"Bearer {self.token}"}, **kw)
        if r.status_code not in ok:
            raise RuntimeError(f"{method} {path} → {r.status_code} {r.text}")
        return r.json()

    def now(self, dt: datetime) -> None:
        # 시계가 다음 달 1일 00:10을 지나가면 그 시각에 먼저 월 마감(서버의 월 마감 루프와 같은 일)
        first = (dt.astimezone(KST).date()).replace(day=1)
        if self.month_mark and first > self.month_mark:
            self.t.move_to(at(first, 0, 10))
            self.month_close()
            self.month_mark = first
        self.t.move_to(dt)

    def month_close(self) -> None:
        """지난달 이달의 MVP: 타이틀 + 발표 기사(바로 게시)."""
        with SessionLocal() as db:
            club = get_club_by_slug(db, CLUB_SLUG)
            ids = mvp_service.close_due_month(db, club)
        for aid in ids:
            article_service.run_generation(aid)

    def login(self) -> None:
        login_limiter.reset()
        self.token = self.call("POST", "/admin/auth", {"password": PIN})["accessToken"]

    # --- 준비
    def setup(self) -> None:
        self.now(at(date(2026, 6, 28), 21))
        self.month_mark = date(2026, 6, 1)
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
        # 3일 전 밤: 일정 생성
        self.now(at(d - timedelta(days=3), 21, rng.randrange(0, 50)))
        self.login()
        sid = self.call("POST", "/sessions", {"sessionDate": d.isoformat(), "title": "토요 정기 경기"})["sessionId"]

        # 전날 밤: 참석 체크
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

        # 당일 07:40 팀 편성 → 일정확정(프리뷰 기사) → 게시
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

        # 마감: [일정마감](주간 자동 타이틀·마감 기사) → 게시(마지막 주는 검토 대기로 둠). 이달의 MVP는 월 마감 때
        end = clock + timedelta(minutes=10)
        self.now(end)
        self.login()
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
    days = weekly(date(2026, 7, 1), date(2026, 10, 17))  # 토요일 16회
    with time_machine.travel(at(date(2026, 6, 28), 21), tick=False) as traveller, TestClient(app) as client:
        sim = Sim(client, traveller)
        writer = TemplateArticleWriter(random.Random(SEED + 1))  # 기본형 기사 작성기. 문구용 난수는 경기 난수와 분리
        article_service.get_writer = lambda: writer
        sim.setup()
        for week, d in enumerate(days):
            sim.play_day(week, d, last=(week == len(days) - 1))
            print(f"{d} 완료")
    with engine.begin() as conn:  # 기사 작성기 표기(OpenAI가 아닌 샘플 템플릿)
        conn.execute(text("UPDATE AI_ARTICLE SET MODEL_NAME = 'sample-template', ERROR_MESSAGE = NULL"))
    print("done:", len(days), "sessions")


if __name__ == "__main__":
    main()
