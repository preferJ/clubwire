"""2026-10-20 추가 기사거리: 듀오·천적·징크스·득점왕 레이스·개근 / 복수·콤비·무패·철벽·첫 골·개인 최다 골.

순수 계산 함수는 가짜 경기 기록으로, 마감(POST) 규칙은 실제 API 흐름으로 확인한다.
"""
from datetime import date

from app.services.history import GoalRecord, MatchRecord
from app.services.stats_service import aggregate_pairs
from app.wire.insight_engine import (
    assist_combos,
    attendance_streak,
    h2h_loss_streak,
    monthly_goal_ranking,
    nemesis_candidates,
    same_team_rate_candidates,
    session_goal_history,
    team_day_records,
)

A, B = 101, 102  # session_team_id


def rec(sid: int, d: date, game: int, team_a: list[int], team_b: list[int], sa: int, sb: int,
        goals: list[tuple[int, int | None, int | None]] = ()) -> MatchRecord:
    """goals: (팀, 득점자, 도움)"""
    win = A if sa > sb else B if sb > sa else None
    r = MatchRecord(match_id=sid * 100 + game, session_id=sid, session_date=d, game_no=game, team_a_id=A, team_b_id=B,
                    score_a=sa, score_b=sb, win_team_id=win, expected_a=None, duration_sec=600)
    r.members = {m: A for m in team_a} | {m: B for m in team_b}
    r.goals = [GoalRecord(event_id=i, team_id=t, scorer_member_id=s, assist_member_id=a, own_goal=False,
                          guest_goal=False, elapsed_sec=60 * i, remaining_sec=600 - 60 * i)
               for i, (t, s, a) in enumerate(goals)]
    return r


def test_duo_jinx_nemesis_candidates():
    d = date(2026, 9, 6)
    hist = []
    # 1·2번: 같은 팀 10경기 8승 / 3·4번: 같은 팀 10경기 2승 / 1번 vs 5번: 맞대결 7경기 1번 6승
    for g in range(10):
        hist.append(rec(1, d, g + 1, [1, 2, 5], [3, 4, 6], 1 if g < 8 else 0, 0 if g < 8 else 1))
    for g in range(7):
        hist.append(rec(2, d, g + 1, [1, 7], [5, 8], 2 if g < 6 else 0, 0 if g < 6 else 1))
    pairs = aggregate_pairs(hist)

    team_of = {1: A, 2: A, 3: B, 4: B, 5: B}
    duo = same_team_rate_candidates(team_of, pairs, 10, min_rate=0.65)
    assert [(a, b) for _, a, b, _ in duo] == [(1, 2)]
    jinx = same_team_rate_candidates(team_of, pairs, 10, max_rate=0.3)
    assert [(a, b) for _, a, b, _ in jinx] == [(3, 4)]
    nem = nemesis_candidates(team_of, pairs, 6, 0.7)
    # 1번(우세) vs 5번(열세): 맞대결 7경기 1번 6승 → 주인공은 열세인 5번
    assert any(und == 5 and dom == 1 and n == 7 and dw == 6 for _, und, dom, n, _, dw in nem)
    # 5번은 최근 1번에게 0연패가 아님(마지막 경기 승리) → 마지막 경기에서 5번 팀이 이김
    assert h2h_loss_streak(hist, 5, 1) == 0
    assert h2h_loss_streak(hist[:-1], 5, 1) >= 6
    # 같은 팀이면 천적 후보가 아니다
    assert nemesis_candidates({1: A, 5: A}, pairs, 6, 0.7) == []


def test_race_attendance_team_day_combo_best():
    sep, aug = date(2026, 9, 6), date(2026, 8, 30)
    hist = [
        rec(1, aug, 1, [1, 2], [3, 4], 3, 0, [(A, 1, 2), (A, 1, 2), (A, 1, None)]),  # 8월 기록은 9월 순위에서 제외
        rec(2, sep, 1, [1, 2], [3, 4], 2, 0, [(A, 1, 2), (A, 2, 1)]),
        rec(2, sep, 2, [1, 2], [3, 4], 0, 0),
        rec(2, sep, 3, [1, 2], [3, 4], 2, 0, [(A, 1, 2), (A, 2, None)]),
        rec(3, date(2026, 9, 13), 1, [1, 3], [2, 4], 1, 1, [(A, 3, None), (B, 2, None)]),
    ]
    assert monthly_goal_ranking(hist, 2026, 9)[:2] == [(2, 3), (1, 2)]
    assert attendance_streak(hist, 1) == 3 and attendance_streak(hist, 9) == 0
    day = team_day_records([r for r in hist if r.session_id == 2])
    assert day[A]["games"] == 3 and day[A]["losses"] == 0 and day[A]["cleanSheets"] == 3 and day[A]["wins"] == 2
    assert assist_combos(hist)[(2, 1)] == 4
    assert session_goal_history(hist, 1) == (3, 3)  # 3일정 출전, 하루 최다 3골(8/30)


def _play(api, sid, goals: list[tuple[str, int, int | None]]):
    """goals: ('A'|'B', 득점자, 도움)"""
    m = api.next_match(sid)
    mid = m["matchId"]
    api.ok(api.post(f"/matches/{mid}/start"))
    side = {m[k]["teamCode"]: m[k]["sessionTeamId"] for k in ("teamA", "teamB")}
    for t, scorer, assist in goals:
        api.ok(api.post(f"/matches/{mid}/goals", {"teamId": side[t], "scorerMemberId": scorer, "assistMemberId": assist}))
    api.ok(api.post(f"/matches/{mid}/end"))
    api.ok(api.post(f"/matches/{mid}/finalize"))
    return m


def test_post_rules_combo_unbeaten_clean_sheet_first_goal(make_club):
    api = make_club("rules2")
    ids = [api.ok(api.post("/members", {"name": f"V{i}"}), 201)["memberId"] for i in range(6)]

    def start_session(day: str):
        sid = api.ok(api.post("/sessions", {"sessionDate": day}), 201)["sessionId"]
        api.ok(api.post(f"/sessions/{sid}/members", {"memberIds": ids}))
        gen = api.ok(api.post(f"/sessions/{sid}/teams/generate", {"teamCount": 2, "seed": 7}))
        conf = api.ok(api.post(f"/sessions/{sid}/teams/confirm", {"generationId": gen["generationId"]}))
        return sid, {t["teamCode"]: [x["memberId"] for x in t["members"]] for t in conf["teams"]}

    # 1일차: 기록만 남김(클럽 첫 기록일 → 첫 골 기사 없음)
    s1, t1 = start_session("2026-11-01")
    _play(api, s1, [("A", t1["A"][0], None)])
    api.ok(api.post(f"/sessions/{s1}/close"))
    first_day = {i["type"] for i in api.ok(api.get("/admin/insights", params={"sessionId": s1}))}
    assert "FIRST_GOAL" not in first_day

    # 2일차: A팀 3경기 무실점 전승, 같은 도움→득점 2번
    s2, t2 = start_session("2026-11-08")
    a1, a2 = t2["A"][0], t2["A"][1]
    _play(api, s2, [("A", a1, a2)])
    _play(api, s2, [("A", a1, a2)])
    _play(api, s2, [("A", a2, None)])
    api.ok(api.post(f"/sessions/{s2}/close"))
    ins = api.ok(api.get("/admin/insights", params={"sessionId": s2}))
    by = {}
    for i in ins:
        by.setdefault(i["type"], []).append(i)

    combo = by["ASSIST_COMBO"][0]["facts"]
    assert combo["assister"]["memberId"] == a2 and combo["scorer"]["memberId"] == a1 and combo["countToday"] == 2
    unbeaten = by["UNBEATEN_TEAM"][0]
    assert unbeaten["facts"]["perfect"] is True and unbeaten["facts"]["games"] == 3
    assert unbeaten["memberId"] is None  # 팀 단위 사실은 대표 선수 없음
    assert by["CLEAN_SHEET"][0]["facts"]["cleanSheets"] == 3
    firsts = {i["facts"]["member"]["memberId"] for i in by.get("FIRST_GOAL", [])}
    assert (a1 in firsts) == (a1 != t1["A"][0]) and (a2 in firsts) == (a2 != t1["A"][0])
    # 새 유형도 태그가 붙는다
    arts = api.ok(api.get("/articles", params={"all": "true", "sessionId": s2}))
    tags = {t for a in arts for t in a["tags"]}
    assert {"콤비", "무패"} <= tags
