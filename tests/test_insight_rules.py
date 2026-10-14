"""POST Insight 판정(결승골/역전/해트트릭/이변)은 Backend가 계산한다."""
from datetime import timedelta

from sqlalchemy import select, update

from app.models import MatchGame, PlayerRating


def test_post_match_insights(make_club, db):
    api = make_club("rules")
    ids = [api.ok(api.post("/members", {"name": f"R{i}"}), 201)["memberId"] for i in range(8)]
    sid = api.ok(api.post("/sessions", {"sessionDate": "2026-11-07"}), 201)["sessionId"]
    api.ok(api.post(f"/sessions/{sid}/members", {"memberIds": ids}))
    gen = api.ok(api.post(f"/sessions/{sid}/teams/generate", {"teamCount": 2, "seed": 3}))
    conf = api.ok(api.post(f"/sessions/{sid}/teams/confirm", {"generationId": gen["generationId"]}))
    teams = {t["teamCode"]: t for t in conf["teams"]}
    b_ids = [m["memberId"] for m in teams["B"]["members"]]
    # B팀을 강팀으로 만들어 '이변' 상황을 만든다(내부 Rating 직접 조정)
    db.execute(update(PlayerRating).where(PlayerRating.member_id.in_(b_ids)).values(current_rating=1300))
    db.commit()

    m = api.next_match(sid)
    mid = m["matchId"]
    api.ok(api.post(f"/matches/{mid}/start"))
    started = db.scalar(select(MatchGame.started_at).where(MatchGame.match_id == mid))
    db.execute(update(MatchGame).where(MatchGame.match_id == mid).values(started_at=started - timedelta(seconds=600)))
    db.commit()
    api.ok(api.post(f"/matches/{mid}/end"))  # 검토 단계(FINISHED)에서 시각을 지정해 기록

    a_team, b_team = m["teamA"]["sessionTeamId"], m["teamB"]["sessionTeamId"]
    d = api.ok(api.get(f"/matches/{mid}"))
    a_ids = [x["memberId"] for x in d["teamA"]["members"]]
    b_play = [x["memberId"] for x in d["teamB"]["members"]]
    assert a_team == teams["A"]["sessionTeamId"] and set(b_play) == set(b_ids)  # 첫 경기 = A vs B
    hero = a_ids[0]
    for sec, team, scorer in [(30, b_team, b_play[0]), (60, b_team, b_play[1]),
                              (200, a_team, hero), (400, a_team, hero), (590, a_team, hero)]:
        api.ok(api.post(f"/matches/{mid}/goals", {"teamId": team, "scorerMemberId": scorer, "elapsedSec": sec}))
    api.ok(api.post(f"/sessions/{sid}/close"))

    ins = api.ok(api.get("/admin/insights", params={"sessionId": sid}))
    by_type = {}
    for i in ins:
        by_type.setdefault(i["type"], []).append(i)
    assert by_type["HAT_TRICK"][0]["facts"]["goals"] == 3
    late = by_type["LATE_WINNER"][0]
    assert late["facts"]["remainingSec"] == 10 and late["facts"]["member"]["memberId"] == hero
    assert by_type["COMEBACK_WIN"][0]["facts"]["maxDeficit"] == 2
    assert by_type["UPSET_WIN"][0]["facts"]["underdogWin"] is True  # 약팀(A) 승리
    # 중요도는 신호 크기에 따라 달라진다(고정값 아님)
    assert 60 < late["importance"] <= 95
    # 자동 타이틀(득점왕) → TITLE_AWARDED
    assert any(i["facts"]["titleName"] == "이주의 득점왕" for i in by_type["TITLE_AWARDED"])
    # Insight에 내부 수치 미노출
    assert all("expected" not in str(i["facts"]).lower() and "rating" not in str(i["facts"]).lower() for i in ins)
