"""일반 회원 경기 조작 — DECISIONS 3-21.

관리자: 일정 생성 · 팀 배정 · 첫 경기 시작 · 경기 중 조작 · 다음 경기 · 기록 확정 · 일정마감
승인된 참가 회원: 경기 중 골 기록 · 일시정지/재개 · 경기 종료, 다음 경기 만들기 · 시작(첫 경기 시작 뒤),
  시작 전 경기 취소(첫 경기 시작 뒤). 기록 확정 · 해제 · 출전 명단 수정 · 시작한 경기 취소 · 일정마감은 관리자만
"""
from sqlalchemy import select

from app.core.database import SessionLocal
from app.models import MatchEvent
from tests.user_helpers import authenticate_member


def _confirmed(api, n=6, date="2027-03-06", teams=2):
    ids = [api.ok(api.post("/members", {"name": f"P{i}"}), 201)["memberId"] for i in range(n)]
    sid = api.ok(api.post("/sessions", {"sessionDate": date}), 201)["sessionId"]
    api.ok(api.post(f"/sessions/{sid}/members", {"memberIds": ids}))
    gen = api.ok(api.post(f"/sessions/{sid}/teams/generate", {"teamCount": teams, "seed": 5}))
    api.ok(api.post(f"/sessions/{sid}/teams/confirm", {"generationId": gen["generationId"]}))
    authenticate_member(api, ids[0])
    return sid, ids


def _code(r):
    return r.status_code, (r.json().get("error") or {}).get("code")


def _member_next(api, sid):
    """일반 회원이 추천 대진 그대로 다음 경기를 만든다."""
    sug = api.ok(api.get(f"/sessions/{sid}/matches/next-suggestion", admin=False))
    return api.ok(api.post(f"/sessions/{sid}/matches/next", {"teamAId": sug["suggestedTeamAId"],
                                                            "teamBId": sug["suggestedTeamBId"]}, admin=False), 201)


def test_first_match_is_admin_then_members_run_the_day(make_club):
    api = make_club("mctl1")
    sid, _ = _confirmed(api)

    # 첫 경기 시작 전(일정확정): 일반 회원은 대진 보기 · 경기 만들기 불가
    assert _code(api.get(f"/sessions/{sid}/matches/next-suggestion", admin=False)) == (403, "FIRST_MATCH_ADMIN_ONLY")
    r = api.post(f"/sessions/{sid}/matches/next", {"teamAId": 1, "teamBId": 2}, admin=False)
    assert _code(r) == (403, "FIRST_MATCH_ADMIN_ONLY")
    # 관리자가 첫 경기를 만든다 → 시작 · 취소도 관리자만
    m1 = api.next_match(sid)["matchId"]
    d1 = api.ok(api.get(f"/matches/{m1}", admin=False))
    assert d1["sessionStatus"] == "CONFIRMED" and d1["status"] == "READY"
    assert _code(api.post(f"/matches/{m1}/start", admin=False)) == (403, "FIRST_MATCH_ADMIN_ONLY")
    assert _code(api.post(f"/matches/{m1}/cancel", admin=False)) == (403, "FIRST_MATCH_ADMIN_ONLY")
    api.ok(api.post(f"/matches/{m1}/start"))
    assert api.ok(api.get(f"/sessions/{sid}", admin=False))["status"] == "IN_PROGRESS"

    # 경기 중: 일반 회원이 골 · 일시정지 · 재개 · 종료
    d1 = api.ok(api.get(f"/matches/{m1}", admin=False))
    a = d1["teamA"]
    api.ok(api.post(f"/matches/{m1}/goals", {"teamId": a["sessionTeamId"], "scorerMemberId": a["members"][0]["memberId"]},
                    admin=False))
    assert api.ok(api.post(f"/matches/{m1}/pause", admin=False))["status"] == "PAUSED"
    assert api.ok(api.post(f"/matches/{m1}/resume", admin=False))["status"] == "RUNNING"
    # 시작한 경기 취소 · 기록 확정은 관리자만
    assert _code(api.post(f"/matches/{m1}/cancel", admin=False)) == (403, "CANCEL_ADMIN_ONLY")
    ended = api.ok(api.post(f"/matches/{m1}/end", admin=False))
    assert ended["status"] == "FINISHED" and ended["finalized"] is False
    assert api.post(f"/matches/{m1}/finalize", admin=False).status_code == 401
    assert _code(api.post(f"/matches/{m1}/cancel", admin=False)) == (403, "CANCEL_ADMIN_ONLY")

    # 다음 경기: 확정 전이어도 일반 회원이 만들고 시작
    sug = api.ok(api.get(f"/sessions/{sid}/matches/next-suggestion", admin=False))
    assert sug["nextGameNo"] == 2 and sug["blockedByMatchId"] is None
    m2 = _member_next(api, sid)
    assert m2["gameNo"] == 2 and m2["status"] == "READY"
    # 대기 중인 경기가 있으면 또 만들 수 없다(관리자와 같은 규칙)
    r = api.post(f"/sessions/{sid}/matches/next", {"teamAId": sug["suggestedTeamAId"], "teamBId": sug["suggestedTeamBId"]},
                 admin=False)
    assert _code(r) == (409, "ACTIVE_MATCH_EXISTS")
    # 잘못 만든 대진(시작 전)은 일반 회원도 취소 → 다시 만들기
    assert api.ok(api.post(f"/matches/{m2['matchId']}/cancel", admin=False))["status"] == "CANCELLED"
    m3 = _member_next(api, sid)
    assert m3["gameNo"] == 3
    assert api.ok(api.post(f"/matches/{m3['matchId']}/start", admin=False))["status"] == "RUNNING"
    api.ok(api.post(f"/matches/{m3['matchId']}/end", admin=False))

    # 일반 회원이 한 조작은 로그인 계정으로 기록된다(이벤트 ADMIN_ID 비움)
    with SessionLocal() as s:
        events = s.scalars(select(MatchEvent).where(MatchEvent.match_id == m3["matchId"])).all()
        assert {e.event_type for e in events} >= {"START", "END"} and all(e.admin_id is None for e in events)
        assert all(e.user_id == api.user_session.user_id for e in events)

    # 출전 명단 수정 · 일정마감은 관리자만. 일정마감 때 확정 안 된 경기는 순서대로 자동 확정
    mem = api.ok(api.get(f"/matches/{m3['matchId']}", admin=False))["teamA"]["members"][0]["memberId"]
    assert api.delete(f"/matches/{m3['matchId']}/members/{mem}", admin=False).status_code == 401
    assert api.post(f"/sessions/{sid}/close", admin=False).status_code == 401
    closed = api.ok(api.post(f"/sessions/{sid}/close"))
    assert closed["status"] == "CLOSED"
    s = api.ok(api.get(f"/sessions/{sid}", admin=False))
    assert [(m["gameNo"], m["status"], m["finalized"]) for m in s["matches"]] == \
        [(1, "FINISHED", True), (2, "CANCELLED", False), (3, "FINISHED", True)]
    # 마감 뒤에는 누구도 경기를 만들 수 없다
    r = api.post(f"/sessions/{sid}/matches/next", {"teamAId": sug["suggestedTeamAId"], "teamBId": sug["suggestedTeamBId"]},
                 admin=False)
    assert r.status_code in (403, 409)


def test_member_controls_after_admin_cancels_first_started_match(make_club):
    """첫 경기를 시작했다가 관리자가 취소해도 일정은 '진행 중' → 일반 회원이 이어서 진행."""
    api = make_club("mctl2")
    sid, _ = _confirmed(api, date="2027-03-13")
    m1 = api.next_match(sid)["matchId"]
    api.ok(api.post(f"/matches/{m1}/start"))
    api.ok(api.post(f"/matches/{m1}/cancel"))
    m2 = _member_next(api, sid)
    assert api.ok(api.post(f"/matches/{m2['matchId']}/start", admin=False))["status"] == "RUNNING"


def test_member_runs_away_match_with_lineup(make_club):
    api = make_club("mctl3")
    ids = [api.ok(api.post("/members", {"name": f"W{i}"}), 201)["memberId"] for i in range(5)]
    sid = api.ok(api.post("/sessions", {"sessionDate": "2027-03-20"}), 201)["sessionId"]
    api.ok(api.post(f"/sessions/{sid}/members", {"memberIds": ids}))
    oid = api.ok(api.post("/opponents", {"name": "한강FC"}), 201)["opponentId"]
    gen = api.ok(api.post(f"/sessions/{sid}/teams/generate", {"teamCount": 1, "opponentId": oid}))
    conf = api.ok(api.post(f"/sessions/{sid}/teams/confirm", {"generationId": gen["generationId"]}))
    authenticate_member(api, ids[0])
    ours = next(t for t in conf["teams"] if not t["opponent"])["sessionTeamId"]
    opp = next(t for t in conf["teams"] if t["opponent"])["sessionTeamId"]
    m1 = api.ok(api.post(f"/sessions/{sid}/matches/next", {"teamAId": ours, "teamBId": opp, "memberIds": ids[:4]}), 201)
    api.ok(api.post(f"/matches/{m1['matchId']}/start"))
    api.ok(api.post(f"/matches/{m1['matchId']}/goals", {"teamId": opp}, admin=False))  # 원정팀 골(점수만)
    api.ok(api.post(f"/matches/{m1['matchId']}/end", admin=False))

    # 일반 회원: 출전 선수를 골라 다음 원정 경기 만들기(직전 명단이 기본값), 명단 없으면 400
    sug = api.ok(api.get(f"/sessions/{sid}/matches/next-suggestion", admin=False))
    assert sug["away"] is True and sug["lineupMemberIds"] == sorted(ids[:4])
    r = api.post(f"/sessions/{sid}/matches/next", {"teamAId": ours, "teamBId": opp}, admin=False)
    assert _code(r) == (400, "LINEUP_REQUIRED")
    m2 = api.ok(api.post(f"/sessions/{sid}/matches/next", {"teamAId": ours, "teamBId": opp, "memberIds": ids[1:]},
                         admin=False), 201)
    d2 = api.ok(api.get(f"/matches/{m2['matchId']}", admin=False))
    assert sorted(x["memberId"] for x in d2["teamA"]["members"]) == sorted(ids[1:])
    # 시작 전 출전 선수 바꾸기는 관리자만
    r = api.post(f"/matches/{m2['matchId']}/members", {"memberId": ids[0], "teamId": ours}, admin=False)
    assert r.status_code == 401
    assert api.ok(api.post(f"/matches/{m2['matchId']}/start", admin=False))["status"] == "RUNNING"
