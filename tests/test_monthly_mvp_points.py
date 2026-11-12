"""이달의 MVP 월간 포인트제(2026-11부터) — DECISIONS 3-18.

- 최종 포인트 = 월간 승점(승 3 · 무 1 · 패 0, 원정 제외) × 실력 점수 배율(월말 ÷ 월초), 소수 둘째 자리
- 후보: 그 달 일정 MONTHLY_MVP_MIN_SESSIONS회 이상 출전 + 승점 1점 이상
- 동점: MVP 수상 횟수 적은 선수 → 그 달 득점 → 그 달 도움 → 어린 선수(출생연도 없거나 같으면 건너뜀) → 공동 수상
- 점수 자체는 어디에도 내보내지 않는다(포인트 · 승점 · 배율만)
"""
import json
from datetime import date, timedelta

import pytest
from sqlalchemy import select

from app.core.database import SessionLocal
from app.core.timeutil import local_today, month_range, prev_month_start
from app.models import AiArticle, MemberTitle, TitleType
from app.services import mvp_service
from app.services.common import get_club_by_slug
from app.services.mvp_service import MonthPoints, MonthRise, _Step, rank_points, tiebreak_info


@pytest.fixture(autouse=True)
def points_rule(monkeypatch):
    """이 파일은 시계와 상관없이 포인트제로 고정한다."""
    monkeypatch.setattr(mvp_service, "POINTS_FROM", date(2000, 1, 1))


def _confirm(api, sid, member_ids):
    api.ok(api.post(f"/sessions/{sid}/members", {"memberIds": member_ids}))
    gen = api.ok(api.post(f"/sessions/{sid}/teams/generate", {"teamCount": 2, "seed": 7}))
    conf = api.ok(api.post(f"/sessions/{sid}/teams/confirm", {"generationId": gen["generationId"]}))
    return {t["teamCode"]: (t["sessionTeamId"], [m["memberId"] for m in t["members"]]) for t in conf["teams"]}


def _match(api, sid, goals):
    """경기 하나(시작 → 골 → 종료 → 확정). goals = [(팀 ID, 득점자, 도움)]"""
    mid = api.next_match(sid)["matchId"]
    api.ok(api.post(f"/matches/{mid}/start"))
    for team, scorer, assist in goals:
        api.ok(api.post(f"/matches/{mid}/goals", {"teamId": team, "scorerMemberId": scorer, "assistMemberId": assist}))
    api.ok(api.post(f"/matches/{mid}/end"))
    api.ok(api.post(f"/matches/{mid}/finalize"))
    return mid


def _mvp_titles(slug):
    with SessionLocal() as s:
        club = get_club_by_slug(s, slug)
        t = s.scalar(select(TitleType).where(TitleType.club_id == club.club_id, TitleType.title_code == "MONTHLY_MVP"))
        return list(s.scalars(select(MemberTitle).where(MemberTitle.title_type_id == t.title_type_id)
                              .order_by(MemberTitle.member_title_id))) if t else []


def _mp(member_id, wins=0, draws=0, losses=0, start=1000.0, end=1000.0, **kw) -> MonthPoints:
    rise = MonthRise(member_id, [_Step(1, 1, date(2026, 11, 7), 1, start, end - start)])
    return MonthPoints(rise, wins=wins, draws=draws, losses=losses, **kw)


def test_points_formula_and_tiebreak_order():
    # 예시: 10승(30점), 실력 점수 1,000 → 1,010 → 30 × 1.01 = 30.3
    p = _mp(1, wins=10, end=1010.0)
    assert (p.win_points, p.ratio, p.points) == (30, 1.01, 30.3)
    # 승 3 · 무 1 · 패 0, 배율은 소수 넷째 자리 · 포인트는 소수 둘째 자리(반올림). 점수가 내려가면 포인트도 깎인다
    q = _mp(2, wins=7, draws=1, losses=4, start=1000.0, end=1012.34)
    assert (q.win_points, q.ratio, q.points) == (22, 1.0123, 22.27)
    assert _mp(3, wins=5, start=1000.0, end=985.0).points == 14.78
    assert _mp(4, wins=1, draws=1, start=1000.0, end=1001.25).points == 4.01  # 4 × 1.0013 = 4.0052

    def ranks(cands):
        return {p.member_id: r for r, p in rank_points(cands)}

    # 포인트가 높은 순
    assert ranks([_mp(1, wins=3), _mp(2, wins=4), _mp(3, wins=3, end=1001.0)]) == {2: 1, 3: 2, 1: 3}
    # ① MVP 수상 횟수가 적은 선수
    a, b = _mp(1, wins=3, mvp_count=2, goals=9), _mp(2, wins=3, mvp_count=1)
    assert ranks([a, b]) == {2: 1, 1: 2}
    assert tiebreak_info(rank_points([a, b])) == {"tiedCount": 2, "decidedBy": "mvpCount",
                                                  "decidedByLabel": "MVP 수상 횟수가 적은 선수", "joint": False}
    # ② 그 달 득점 → ③ 그 달 도움
    assert ranks([_mp(1, wins=3, goals=2, assists=5), _mp(2, wins=3, goals=3)]) == {2: 1, 1: 2}
    c, d = _mp(1, wins=3, goals=2, assists=1), _mp(2, wins=3, goals=2, assists=2)
    assert ranks([c, d]) == {2: 1, 1: 2} and tiebreak_info(rank_points([c, d]))["decidedBy"] == "assists"
    # ④ 나이가 어린 선수(출생연도가 늦은 선수)
    e, f = _mp(1, wins=3, birth_year=1990), _mp(2, wins=3, birth_year=1996)
    assert ranks([e, f]) == {2: 1, 1: 2} and tiebreak_info(rank_points([e, f]))["decidedBy"] == "age"
    # ⑤ 출생연도가 한 명이라도 없거나 같으면 나이로 가리지 않고 공동 수상
    g, h = _mp(1, wins=3, birth_year=1990), _mp(2, wins=3)
    assert ranks([g, h]) == {1: 1, 2: 1}
    assert tiebreak_info(rank_points([g, h])) == {"tiedCount": 2, "decidedBy": None, "decidedByLabel": None, "joint": True}
    assert ranks([_mp(1, wins=3, birth_year=1992), _mp(2, wins=3, birth_year=1992), _mp(3, wins=2)]) == {1: 1, 2: 1, 3: 3}
    # 셋이 같은 포인트: 수상 횟수로 한 명이 빠지고 남은 둘은 끝까지 같아 공동 수상
    three = rank_points([_mp(1, wins=3, mvp_count=1), _mp(2, wins=3), _mp(3, wins=3)])
    assert {p.member_id: r for r, p in three} == {2: 1, 3: 1, 1: 3}
    assert tiebreak_info(three) == {"tiedCount": 3, "decidedBy": "mvpCount",
                                    "decidedByLabel": "MVP 수상 횟수가 적은 선수", "joint": True}
    # 혼자 1위면 동점 정보 없음
    assert tiebreak_info(rank_points([_mp(1, wins=4), _mp(2, wins=3)])) is None


def test_monthly_points_race_close_award_and_article(make_club):
    api = make_club("mvppt")
    ids = [api.ok(api.post("/members", {"name": n}), 201)["memberId"]
           for n in ("홍길동", "김철수", "이영희", "박민수", "최지훈", "정다은")]
    month = prev_month_start(local_today("Asia/Seoul"))  # 지난달 = 월 마감 대상
    start, end = month_range(month)
    s1 = api.ok(api.post("/sessions", {"sessionDate": month.replace(day=3).isoformat()}), 201)["sessionId"]
    s2 = api.ok(api.post("/sessions", {"sessionDate": month.replace(day=10).isoformat()}), 201)["sessionId"]

    # 1차(6명): A 승 · A 승 · 무승부 / 2차(5명, 정다은 결석): A 승 · B 승
    t1 = _confirm(api, s1, ids)
    (a1, a1m), (b1, b1m) = t1["A"], t1["B"]
    _match(api, s1, [(a1, a1m[0], a1m[1])])
    _match(api, s1, [(a1, a1m[0], None), (a1, a1m[1], a1m[0]), (b1, b1m[0], None)])
    _match(api, s1, [(a1, a1m[2], None), (b1, b1m[1], b1m[0])])
    t2 = _confirm(api, s2, ids[:5])
    (a2, a2m), (b2, b2m) = t2["A"], t2["B"]
    _match(api, s2, [(a2, a2m[0], None)])
    _match(api, s2, [(b2, b2m[0], b2m[1])])

    # 기대값: 화면에 나오지 않는 점수 이력(DB)과 경기 결과로 직접 계산
    wdl = {m: [0, 0, 0] for m in ids}
    for won, lost in ((a1m, b1m), (a1m, b1m), (a2m, b2m), (b2m, a2m)):
        for m in won:
            wdl[m][0] += 1
        for m in lost:
            wdl[m][2] += 1
    for m in a1m + b1m:
        wdl[m][1] += 1
    expected = {}
    for m in ids[:5]:  # 정다은은 일정 1회 → 자격 없음
        h = api.rating_history_db(m)
        win_points = wdl[m][0] * 3 + wdl[m][1]
        ratio = mvp_service._q(h[-1]["after"] / h[0]["before"], 4)
        if win_points:
            expected[m] = (mvp_service._q(win_points * ratio, 2), win_points, ratio)
    assert len({v[1] for v in expected.values()}) > 1, "승점이 갈리는 시나리오"

    # 그 달 중간: 후보 1~3위(포인트 · 승점 · 배율), 점수 자체는 없음
    with SessionLocal() as s:
        club = get_club_by_slug(s, "mvppt")
        race = mvp_service.mvp_race(s, club, today=month.replace(day=20))
        ranked = mvp_service.points_ranking(s, club.club_id, start, end, 2)
    assert race["basis"] == "points" and race["minSessions"] == 2 and race["lastMonth"] is None
    assert {p.member_id: (p.points, p.win_points, p.ratio) for _, p in ranked} == expected
    assert [c["points"] for c in race["candidates"]] == sorted((v[0] for v in expected.values()), reverse=True)[:3]
    assert all(set(c) == {"rank", "memberId", "name", "points", "winPoints", "ratio", "wins", "draws", "losses",
                          "sessions", "games"} for c in race["candidates"])
    top = race["candidates"][0]
    assert top["rank"] == 1 and (top["wins"], top["draws"], top["losses"]) == tuple(wdl[top["memberId"]])
    assert ids[5] not in [p.member_id for _, p in ranked]
    assert "rating" not in json.dumps(race).lower()

    # 월 마감: 타이틀(포인트 1위) + 기사(바로 게시)
    api.ok(api.post(f"/sessions/{s1}/close"))
    assert _mvp_titles("mvppt") == []
    api.ok(api.post(f"/sessions/{s2}/close"))
    titles = _mvp_titles("mvppt")
    best = max(v[0] for v in expected.values())
    winners = sorted(m for m, v in expected.items() if v[0] == best)
    assert sorted(t.member_id for t in titles) == winners
    f = titles[0].facts_json
    assert (titles[0].period_start, titles[0].period_end, titles[0].session_id) == (start, end, s2)
    assert f["metric"] == "mvpPoints" and f["value"] == best and f["tied"] == (len(winners) > 1)
    assert (f["winPoints"], f["ratio"]) == expected[titles[0].member_id][1:] and f["sessions"] == 2

    art = next(a for a in api.ok(api.get("/articles", admin=False)) if a["articleType"] == "MONTHLY_MVP")
    detail = api.ok(api.get(f"/articles/{art['articleId']}", admin=False))
    text = f"{detail['title']}\n{detail['summary']}\n{detail['content']}"
    names = {m["memberId"]: m["name"] for m in api.ok(api.get("/members"))}
    assert all(names[m] in detail["title"] for m in winners) and "이달의 MVP" in art["tags"]
    pt = f"{best:.2f}".rstrip("0").rstrip(".")
    assert f"월간 포인트 {pt}점" in text and f"승점은 {f['winPoints']}점" in text and "실력 점수 배율" in text
    assert "승점을 가장 많이 쌓은 날" in text and "선정 기준은 월간 승점" in text
    assert "레이팅" not in text and "rating" not in text.lower() and "상승률" not in text
    with SessionLocal() as s:
        req = s.get(AiArticle, art["articleId"]).request_json
    payload = json.dumps(req, ensure_ascii=False)
    assert req["monthlyMvp"]["basis"] == "points" and req["monthlyMvp"]["winners"][0]["points"] == best
    for m in ids:
        for h in api.rating_history_db(m):  # 점수(예: 1010.3)는 AI 입력에도 넣지 않음
            assert f"{h['after']:.1f}" not in payload and f"{h['before']:.2f}" not in payload

    # 수상 내역 · 다음 달 홈 화면의 '지난달 MVP'
    awards = [a for a in api.ok(api.get("/titles/awards", admin=False)) if a["titleCode"] == "MONTHLY_MVP"]
    assert awards and awards[0]["facts"]["metric"] == "mvpPoints"
    with SessionLocal() as s:
        club = get_club_by_slug(s, "mvppt")
        last = mvp_service.mvp_race(s, club, today=end + timedelta(days=3))["lastMonth"]
    assert last["winners"][0] == {"memberId": titles[0].member_id, "name": names[titles[0].member_id],
                                  "metric": "mvpPoints", "value": best, "risePercent": None}
    # 한 달은 한 번만
    with SessionLocal() as s:
        club = get_club_by_slug(s, "mvppt")
        assert mvp_service.close_due_month(s, club) == []


def test_points_tie_goes_to_fewer_mvps_then_goals_then_younger(make_club):
    """전 경기 1:1 무승부 → 모두 같은 포인트. 수상 횟수 · 득점 · 도움 · 나이 순으로 가린다."""
    api = make_club("mvptie")
    ids = [api.ok(api.post("/members", {"name": n}), 201)["memberId"]
           for n in ("홍길동", "김철수", "이영희", "박민수", "최지훈", "정다은")]
    x, y, others = ids[0], ids[1], ids[2:]
    month = prev_month_start(local_today("Asia/Seoul"))
    start, end = month_range(month)
    # 나머지 네 명은 이전에 'MVP로 세는' 타이틀을 한 번씩 받았다
    api.ok(api.post("/titles/types", {"titleCode": "SPECIAL_MVP", "titleName": "특별 MVP", "countsAsMvp": True}), 201)
    for m in others:
        api.ok(api.post("/titles/awards", {"titleCode": "SPECIAL_MVP", "memberId": m,
                                           "awardDate": (start - timedelta(days=40)).isoformat()}), 201)

    for day in (5, 12):
        sid = api.ok(api.post("/sessions", {"sessionDate": month.replace(day=day).isoformat()}), 201)["sessionId"]
        teams = _confirm(api, sid, ids)
        (ta, am), (tb, bm) = teams["A"], teams["B"]
        side = {m: ta for m in am} | {m: tb for m in bm}
        spare = {ta: next(m for m in am if m in others), tb: next(m for m in bm if m in others)}
        if side[x] != side[y]:  # 다른 팀: 첫 경기에서 서로 한 골씩, 둘째 경기는 다른 선수들이
            _match(api, sid, [(side[x], x, None), (side[y], y, None)])
            _match(api, sid, [(ta, spare[ta], None), (tb, spare[tb], None)])
        else:  # 같은 팀: 한 경기씩 번갈아 득점
            other = tb if side[x] == ta else ta
            _match(api, sid, [(side[x], x, None), (other, spare[other], None)])
            _match(api, sid, [(side[y], y, None), (other, spare[other], None)])
        api.ok(api.post(f"/sessions/{sid}/close")) if day == 5 else None
        last_sid = sid

    def race():
        with SessionLocal() as s:
            club = get_club_by_slug(s, "mvptie")
            return mvp_service.mvp_race(s, club, today=month.replace(day=20))["candidates"]

    # 모두 4무(승점 4) × 1.0 = 4. 수상 횟수 0회인 홍길동 · 김철수가 앞서고, 득점(2골) · 도움(0)도 같다 → 출생연도가 없어 공동 1위
    cands = race()
    assert {c["points"] for c in cands} == {4.0} and {c["winPoints"] for c in cands} == {4}
    assert sorted((c["rank"], c["memberId"]) for c in cands[:2]) == [(1, x), (1, y)] and cands[2]["rank"] == 3
    # 출생연도를 넣으면 어린 선수(김철수, 1997년생)가 1위
    api.ok(api.patch(f"/members/{x}", {"birthYear": 1990}))
    api.ok(api.patch(f"/members/{y}", {"birthYear": 1997}))
    cands = race()
    assert [(c["rank"], c["memberId"]) for c in cands[:2]] == [(1, y), (2, x)]

    api.ok(api.post(f"/sessions/{last_sid}/close"))  # 월 마감
    titles = _mvp_titles("mvptie")
    assert [t.member_id for t in titles] == [y] and titles[0].facts_json["tied"] is False
    art = next(a for a in api.ok(api.get("/articles", admin=False)) if a["articleType"] == "MONTHLY_MVP")
    detail = api.ok(api.get(f"/articles/{art['articleId']}", admin=False))
    assert "최종 포인트가 같은 선수가 6명이었고, 나이가 어린 선수를 우선하는 기준에 따라 김철수가 선정됐다." in detail["content"]
    assert api.ok(api.get(f"/articles/{art['articleId']}"))["requestJson"]["monthlyMvp"]["tiebreak"] == {
        "tiedCount": 6, "decidedBy": "age", "decidedByLabel": "나이가 어린 선수", "joint": False}
