"""기본형 기사 작성기(템플릿).

- OpenAI 키가 없을 때(AI_PROVIDER=auto/stub) 기사를 이 템플릿으로 쓴다.
- OpenAI 호출이 실패하면(크레딧 · 지출 한도 초과, 연결 오류, 응답 검증 실패) article_service가 이걸로 대신 쓴다.
- 샘플 데이터 생성기(scripts/gen_sample_data.py)도 같은 작성기를 쓴다(원래 그 파일에 있던 SampleArticleWriter를 옮김).
- 입력은 AI와 같은 DTO(build_payload). 사실 밖 내용은 쓰지 않고, 조사(이/가 · 은/는 …)는 받침으로 고른다.
"""
from __future__ import annotations

import random
from datetime import date
from typing import Any

from app.integrations.openai.writer import validate_draft


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
               "CLOSE_MATCH_EXPECTED": -8, "MILESTONE_EXPECTED": -10, "MILESTONE_ACHIEVED": -4,
               "REVENGE_RESULT": 16, "NEMESIS_MATCH": 10, "PERSONAL_BEST_GOALS": 12, "ASSIST_COMBO": 8,
               "DUO_REUNITED": 6, "SCORING_RACE": 6, "UNBEATEN_TEAM": 6, "JINX_PAIR": 4, "CLEAN_SHEET": 4,
               "ATTENDANCE_STREAK": -2}
_METRIC = {"games": ("경기 출전", "경기"), "goals": ("골", "골"), "assists": ("도움", "개")}


def _milestone(metric: str, ms: int) -> str:
    word, _ = _METRIC.get(metric, ("골", "골"))
    return f"통산 {ms}{word}" if metric != "games" else f"통산 {ms}경기 출전"


class TemplateArticleWriter:
    """기본형 기사: Insight 사실만으로 쓰는 템플릿 기사(사실 밖 내용은 쓰지 않는다). 같은 유형 사실은 한 문장으로 묶는다.

    rng: 문구 변형용 난수. 없으면 기사마다(일정 날짜 · 종류) 같은 결과가 나오게 고정 시드를 쓴다.
    """

    provider = "template"

    def __init__(self, rng: random.Random | None = None):
        self._own_rng = rng
        self.rng = rng

    @staticmethod
    def _name(ins: dict[str, Any]) -> str:
        f = ins.get("facts") or {}
        return (ins.get("subject") or {}).get("name") or (f.get("member") or {}).get("name") or ""

    def _group_key(self, ins: dict[str, Any], phase: str) -> tuple:
        t, f = ins["type"], ins.get("facts") or {}
        if t in ("WIN_STREAK", "SCORING_STREAK", "ATTENDANCE_STREAK"):
            return (t, phase)
        if t in ("FIRST_GOAL", "FIRST_ASSIST"):
            return (t,)
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
            if t == "ATTENDANCE_STREAK":
                ranked = sorted(items, key=lambda i: -(i.get("facts") or {}).get("streak", 0))
                tagged = [(self._name(i), f"{i['facts']['streak']}주") for i in ranked if self._name(i)]
                top, top_s = tagged[0][0], ranked[0]["facts"]["streak"]
                if len(tagged) == 1:
                    return f"{top}, {top_s}주 연속 개근", f"{j(top, '은', '는')} 오늘로 {top_s}주 연속 출전이다."
                body_, last = tagged_list(tagged)
                return f"{top}, {top_s}주 연속 개근", f"{body_}{josa_only(last, '이', '가')} 개근 행진을 이어가고 있다."
            if t in ("DUO_REUNITED", "JINX_PAIR"):
                ms = [m.get("name") for m in f.get("members", []) if m.get("name")]
                pair, both = f"{ms[0]}·{ms[1]}", names_ko(ms)
                m_, w_ = f["sameTeamMatches"], f["sameTeamWins"]
                if t == "DUO_REUNITED":
                    return (f"{pair}, 다시 한 팀… 함께 {m_}경기 {w_}승",
                            f"{j(both, '이', '가')} 다시 한 팀이 됐다. 같은 팀으로 뛴 {m_}경기에서 {w_}승을 거둔 조합이다.")
                return (f"{pair}, 징크스 깰까",
                        f"{j(both, '은', '는')} 같은 팀으로 {m_}경기에서 {w_}승에 그쳤다. 오늘은 징크스를 깰 수 있을까.")
            if t == "NEMESIS_MATCH":
                u, r = f["member"]["name"], f["rival"]["name"]
                uw, dw, dr, ls = f["memberWins"], f["rivalWins"], f["draws"], f.get("lossStreak", 0)
                streak_txt = f" 최근 {ls}연패 중이다." if ls >= 2 else ""
                rec_txt = f"{uw}승 {dr}무 {dw}패" if dr else f"{uw}승 {dw}패"
                return (f"{u}, {r} 상대 {uw}승 {dw}패… 설욕할까",
                        f"{j(u, '은', '는')} {r} 상대로 {rec_txt}.{streak_txt} 오늘은 다른 팀으로 갈려 설욕을 노린다.")
            if t == "REVENGE_RESULT":
                u, r = f["member"]["name"], f["rival"]["name"]
                uw, dw, ls, oc = f["memberWinsToday"], f["rivalWinsToday"], f.get("lossStreakBefore", 0), f["outcome"]
                if oc == "REVENGE":
                    head = f"{u}, {r} 상대 {ls}연패 끊었다" if ls >= 2 else f"{u}, {r}에게 설욕"
                    return head, f"{j(u, '은', '는')} 오늘 {j(r, '과', '와')}의 맞대결에서 {uw}승 {dw}패로 앞서며 설욕에 성공했다."
                if oc == "HELD":
                    return (f"{r}, {u} 상대 강세 이어가",
                            f"{j(r, '은', '는')} 오늘도 {u} 상대로 {dw}승을 챙기며 강세를 이어갔다.")
                if uw == dw == 0:
                    return None, f"{j(u, '과', '와')} {j(r, '은', '는')} 오늘 {f['drawsToday']}번 맞붙어 모두 비겼다."
                return None, f"{j(u, '과', '와')} {r}의 맞대결은 오늘 {uw}승 {dw}패로 팽팽했다."
            if t == "SCORING_RACE":
                mo, ld, ch = f["month"], f["leader"]["name"], f["chaser"]["name"]
                lg, cg, gap = f["leaderGoals"], f["chaserGoals"], f["gap"]
                if gap == 0:
                    return (f"{mo}월 득점왕, {ld}·{ch} 공동 선두",
                            f"{mo}월 득점 경쟁이 뜨겁다. {j(names_ko([ld, ch]), '이', '가')} 나란히 {lg}골로 공동 선두다.")
                return (f"{mo}월 득점왕, {ld}·{ch} {gap}골 차",
                        f"{mo}월 득점 경쟁이 뜨겁다. {j(ld, '이', '가')} {lg}골, {j(ch, '이', '가')} {cg}골로 {gap}골 차다.")
            if t == "ASSIST_COMBO":
                a_, s_, n_, c_ = f["assister"]["name"], f["scorer"]["name"], f["countToday"], f.get("careerCount", 0)
                tail = f" 둘이 합작한 골은 통산 {c_}골이다." if c_ > n_ else ""
                cnt = {2: "두", 3: "세", 4: "네", 5: "다섯"}.get(n_, str(n_))
                return (f"{a_}→{s_}, 오늘만 {cnt} 번",
                        f"{a_}의 패스를 {j(s_, '이', '가')} 마무리한 골이 오늘만 {cnt} 번 나왔다.{tail}")
            if t in ("UNBEATEN_TEAM", "CLEAN_SHEET"):
                team = f["teamCode"] + "팀"
                if t == "CLEAN_SHEET":
                    return (f"{team}, {f['cleanSheets']}경기 무실점",
                            f"{j(team, '은', '는')} 오늘 {f['games']}경기 중 {f['cleanSheets']}경기를 무실점으로 막아 냈다.")
                if f.get("perfect"):
                    return f"{team}, {f['games']}전 전승", f"{j(team, '은', '는')} 오늘 {f['games']}경기를 모두 이겼다."
                return (f"{team}, 오늘 {f['games']}경기 무패",
                        f"{j(team, '은', '는')} 오늘 {f['games']}경기에서 {f['wins']}승 {f['draws']}무로 한 번도 지지 않았다.")
            if t in ("FIRST_GOAL", "FIRST_ASSIST"):
                what = "첫 골을 신고했다" if t == "FIRST_GOAL" else "첫 도움을 기록했다"
                return (f"{head_who}, {'첫 골 신고' if t == 'FIRST_GOAL' else '첫 도움'}",
                        f"{j(who, '이', '가')} {'나란히 ' if many else ''}기록 집계 후 {what}.")
            if t == "PERSONAL_BEST_GOALS":
                g_, pb = f["goalsToday"], f["previousBest"]
                return (f"{lead}, 하루 {g_}골 개인 최다",
                        f"{j(lead, '은', '는')} 오늘 {g_}골을 넣어 하루 최다 기록({pb}골)을 넘어섰다.")
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
                if f.get("metric") == "attendStreak":  # '연속 참가 10회' — 이름에 횟수가 있음
                    return (f"{head_who}, {tn}",
                            f"{j(who, '이', '가')} {'나란히 ' if many else ''}{tn}를 달성했다. 한 번도 빠지지 않고 나온 기록이다.")
                unit = {"assists": "도움", "wins": "승"}.get(f.get("metric"), "골")
                val = f"({f['value']}{unit})" if f.get("value") else ""
                return (f"{head_who}, {tn}",
                        f"{j(who, '이', '가')} {'나란히 ' if many else ''}{tn}{val}에 이름을 올렸다.")
        except (KeyError, TypeError, IndexError):
            return None, None
        return None, None

    def write(self, payload: dict[str, Any], model: str, options: dict[str, Any] | None = None):
        if self._own_rng is None and self.rng is None:  # 같은 사실이면 같은 문장(다시 써도 결과가 안 흔들림)
            self.rng = random.Random(f"{payload.get('articleType')}:{payload.get('sessionDate')}:{payload.get('month')}")
        kind = payload.get("articleType")
        if kind == "MONTHLY_MVP":
            return self._monthly_mvp(payload)
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
            lead = f"{md} {'월화수목금토일'[d.weekday()]}요일, {club} {total}명이 {len(teams)}개 팀으로 나뉘어 맞붙는다."
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


    RESULT = {"W": "승리", "D": "무승부", "L": "패배"}

    def _monthly_mvp(self, payload: dict[str, Any]):
        """이달의 MVP 발표: 상승률 · 한 달 성적 · 특히 많이 오른 경기 · 가장 크게 오른 날 · 2·3위 · 선정 기준."""
        mvp = payload.get("monthlyMvp") or {}
        month = payload.get("monthLabel") or ""
        winners = mvp.get("winners") or []
        w = winners[0]
        names = names_ko([x["name"] for x in winners])
        tied = len(winners) > 1
        title = f"{month} 이달의 MVP, {names}" + (" 공동 수상" if tied else "")
        summary = (f"{j(names, '이', '가')} {month} 실력 점수를 {w['risePercent']:.1f}% 끌어올리며 "
                   f"{month} MVP{'를 함께 차지했다' if tied else '에 올랐다'}.")
        paras = []
        for x in winners:
            rec = f"{x['wins']}승 {x['draws']}무 {x['losses']}패"
            gl = [f"{x['goals']}골"] if x["goals"] else []
            gl += [f"{x['assists']}도움"] if x["assists"] else []
            paras.append(f"{j(x['name'], '은', '는')} {month} {x['sessions']}번의 일정, {x['games']}경기에 나서 {rec}"
                         + (f", {' '.join(gl)}" + josa_only(gl[-1], "을", "를") + " 기록했다." if gl else "를 기록했다.")
                         + f" 한 달 동안 실력 점수는 {x['risePercent']:.1f}% 올랐다.")
            best = [m for m in x.get("bestMatches", []) if m.get("result")]
            if best:
                parts = []
                for m in best:
                    md = date.fromisoformat(m["sessionDate"])
                    pts = [f"{m['goals']}골"] if m.get("goals") else []
                    pts += [f"{m['assists']}도움"] if m.get("assists") else []
                    who = f", 본인 {' '.join(pts)}" if pts else ""
                    parts.append(f"{md.month}월 {md.day}일 {m['gameNo']}경기 TEAM {m['teamCode']} {m['score']} "
                                 f"TEAM {m['opponentTeamCode']} {self.RESULT[m['result']]}{who}(+{m['risePercent']:.1f}%)")
                paras.append("특히 많이 오른 경기는 " + ", ".join(parts) + "이다.")
            day = x.get("bestDay")
            if day:
                dd = date.fromisoformat(day["sessionDate"])
                pts = [f"{day['goals']}골"] if day["goals"] else []
                pts += [f"{day['assists']}도움"] if day["assists"] else []
                tail = pts[-1] if pts else f"{day['wins']}승"
                paras.append(f"가장 크게 오른 날은 {dd.month}월 {dd.day}일이다. 이날 {day['games']}경기에서 {day['wins']}승"
                             + (f", {' '.join(pts)}" if pts else "") + josa_only(tail, "으로", "로")
                             + f" 한 번에 {day['risePercent']:.1f}%를 쌓았다.")
        runners = mvp.get("runnersUp") or []
        if runners:
            seq = [f"{r['rank']}위 {r['name']}(+{r['risePercent']:.1f}%)" for r in runners]
            paras.append("뒤를 이어 " + ", ".join(seq) + josa_only(runners[-1]["name"], "이", "가")
                         + " 이름을 올렸다.")
        titles = [x for x in mvp.get("monthlyTitles") or [] if x.get("names")]
        if titles:
            unit = {"goals": "골", "assists": "도움"}
            parts = [f"{x['titleName'].replace('이달의 ', '')}{josa_only(x['titleName'], '은', '는')} "
                     f"{names_ko(x['names'])}({x['value']}{unit.get(x.get('metric'), '')}{', 공동' if len(x['names']) > 1 else ''})"
                     for x in titles]
            paras.append(f"{month} " + ", ".join(parts) + "이다.")
        if mvp.get("rule"):
            paras.append(f"선정 기준은 {mvp['rule']}다.")
        raw = {"title": title[:120], "summary": summary[:300], "body": "\n\n".join(paras), "usedInsightIds": []}
        return validate_draft(raw, payload), raw
