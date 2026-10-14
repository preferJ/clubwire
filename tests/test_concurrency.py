"""LIVE 연타: Lost Update / Double Goal 방지 (행 잠금 + 멱등키)."""
from concurrent.futures import ThreadPoolExecutor

from sqlalchemy import func, select

from app.core.database import SessionLocal
from app.models import MatchEvent, MatchGame
from app.services import match_service


def test_concurrent_goals(make_club, db):
    api = make_club("rush")
    ids = [api.ok(api.post("/members", {"name": f"C{i}"}), 201)["memberId"] for i in range(4)]
    sid = api.ok(api.post("/sessions", {"sessionDate": "2026-12-05"}), 201)["sessionId"]
    api.ok(api.post(f"/sessions/{sid}/members", {"memberIds": ids}))
    gen = api.ok(api.post(f"/sessions/{sid}/teams/generate", {"teamCount": 2}))
    api.ok(api.post(f"/sessions/{sid}/teams/confirm", {"generationId": gen["generationId"]}))
    m = api.next_match(sid)
    mid, team = m["matchId"], m["teamA"]["sessionTeamId"]
    api.ok(api.post(f"/matches/{mid}/start"))
    scorer = api.ok(api.get(f"/matches/{mid}"))["teamA"]["members"][0]["memberId"]
    club_id = api.ok(api.get(""))["clubId"]

    def goal(key):
        with SessionLocal() as s:
            return match_service.add_goal(s, club_id, mid, None, team_id=team, scorer_member_id=scorer,
                                          idempotency_key=key)[2]

    with ThreadPoolExecutor(8) as ex:
        distinct = list(ex.map(goal, [f"k{i}" for i in range(12)]))
        same = list(ex.map(goal, ["dup"] * 8))
    assert all(distinct) and sum(same) == 1
    score = db.scalar(select(MatchGame.score_a).where(MatchGame.match_id == mid))
    events = db.scalar(select(func.count()).select_from(MatchEvent).where(
        MatchEvent.match_id == mid, MatchEvent.event_type == "GOAL"))
    assert score == events == 13
