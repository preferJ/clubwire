"""경기 조작은 승인된 해당 일정 참석자 또는 관리자로 제한한다."""
from uuid import uuid4

import pytest
from sqlalchemy import select

from app.core.database import SessionLocal
from app.core.timeutil import utcnow
from app.models import MatchEvent, Member, SessionMember
from app.models.user import AppUser, MemberAccountLink
from tests.user_helpers import make_user_session


@pytest.fixture
def game(make_club):
    api = make_club(f"access-{uuid4().hex[:10]}")
    ids = [api.ok(api.post("/members", {"name": f"선수{i}"}), 201)["memberId"] for i in range(6)]
    sid = api.ok(api.post("/sessions", {"sessionDate": "2027-04-10"}), 201)["sessionId"]
    api.ok(api.post(f"/sessions/{sid}/members", {"memberIds": ids}))
    generation = api.ok(api.post(f"/sessions/{sid}/teams/generate", {"teamCount": 2, "seed": 1}))
    api.ok(api.post(f"/sessions/{sid}/teams/confirm", {"generationId": generation["generationId"]}))
    mid = api.next_match(sid)["matchId"]
    api.ok(api.post(f"/matches/{mid}/start"))
    return api, sid, mid, ids


def _request(api, method, path, headers=None, body=None):
    # Cookie 헤더를 명시해서 세션 범위 TestClient의 쿠키와 독립적으로 검증한다.
    return api.c.request(method, api.url(path), headers=headers or {"Cookie": ""}, json=body)


def test_anonymous_browsing_is_public_but_all_game_controls_require_login(game):
    api, sid, mid, _ = game
    detail = api.ok(_request(api, "GET", f"/matches/{mid}"))
    api.ok(_request(api, "GET", f"/sessions/{sid}"))
    api.ok(_request(api, "GET", "/live"))
    team = detail["teamA"]
    body = {"teamId": team["sessionTeamId"], "scorerMemberId": team["members"][0]["memberId"]}
    eid = api.ok(api.post(f"/matches/{mid}/goals", body))["eventId"]
    for method, path, payload in [
        ("GET", f"/sessions/{sid}/matches/next-suggestion", None),
        ("POST", f"/sessions/{sid}/matches/next", {
            "teamAId": detail["teamA"]["sessionTeamId"], "teamBId": detail["teamB"]["sessionTeamId"]}),
        *(("POST", f"/matches/{mid}/{action}", None) for action in ("start", "pause", "resume", "end", "cancel")),
        ("POST", f"/matches/{mid}/goals", body),
        ("PATCH", f"/matches/{mid}/events/{eid}", body),
        ("POST", f"/matches/{mid}/events/{eid}/cancel", None),
    ]:
        response = _request(api, method, path, body=payload)
        assert response.status_code == 401, (method, path, response.text)
    after = api.ok(api.get(f"/matches/{mid}"))
    assert after["status"] == "RUNNING" and after["teamA"]["score"] == 1


@pytest.mark.parametrize("kind", ["unlinked", "pending", "nonattendee"])
def test_logged_in_but_unapproved_or_absent_member_cannot_control(game, kind):
    api, sid, mid, ids = game
    if kind == "nonattendee":
        member_id = api.ok(api.post("/members", {"name": "오늘 불참"}), 201)["memberId"]
        user = make_user_session(api, member_id)
    else:
        user = make_user_session(api, ids[0] if kind == "pending" else None, pending=kind == "pending")
    assert _request(api, "POST", f"/matches/{mid}/pause", user.headers).status_code == 403
    assert _request(api, "GET", f"/sessions/{sid}/matches/next-suggestion", user.headers).status_code == 403
    assert api.ok(api.get(f"/matches/{mid}"))["status"] == "RUNNING"


def test_user_link_in_another_club_does_not_grant_control(game, make_club):
    api, _, mid, _ = game
    elsewhere = make_club(f"elsewhere-{uuid4().hex[:10]}")
    other_id = elsewhere.ok(elsewhere.post("/members", {"name": "다른 팀 선수"}), 201)["memberId"]
    user = make_user_session(elsewhere, other_id)
    assert _request(api, "POST", f"/matches/{mid}/pause", user.headers).status_code == 403
    assert api.ok(api.get(f"/matches/{mid}"))["status"] == "RUNNING"


def test_csrf_required_for_member_writes_but_not_safe_reads(game):
    api, sid, mid, ids = game
    user = make_user_session(api, ids[0])
    cookie_only = {"Cookie": user.headers["Cookie"]}
    api.ok(_request(api, "GET", f"/sessions/{sid}/matches/next-suggestion", cookie_only))
    for headers in (cookie_only, {**cookie_only, "X-CSRF-Token": "invalid"}):
        assert _request(api, "POST", f"/matches/{mid}/pause", headers).status_code == 403
    assert api.ok(_request(api, "POST", f"/matches/{mid}/pause", user.headers))["status"] == "PAUSED"
    # 관리자 Bearer 인증은 회원 쿠키/CSRF 토큰 없이도 기존처럼 동작한다.
    assert api.ok(api.post(f"/matches/{mid}/resume"))["status"] == "RUNNING"


def test_session_access_matches_effective_participant_permissions(game):
    api, sid, _, ids = game
    path = f"/sessions/{sid}/access"
    anonymous = api.ok(_request(api, "GET", path))
    assert anonymous == {"sessionId": sid, "canControl": False, "reason": "LOGIN_REQUIRED"}
    pending = make_user_session(api, ids[1], pending=True)
    assert api.ok(_request(api, "GET", path, pending.headers))["reason"] == "LINK_REQUIRED"
    user = make_user_session(api, ids[0])
    assert api.ok(_request(api, "GET", path, user.headers)) == {
        "sessionId": sid, "canControl": True, "reason": None}
    with SessionLocal() as db:
        attendee = db.scalar(select(SessionMember).where(SessionMember.session_id == sid,
                                                        SessionMember.member_id == ids[0]))
        attendee.attendance_status = "ABSENT"
        db.commit()
    assert api.ok(_request(api, "GET", path, user.headers))["reason"] == "ATTENDANCE_REQUIRED"
    assert api.ok(api.get(path))["canControl"] is True


@pytest.mark.parametrize("revocation", ["attendance", "inactive", "deleted", "unlink"])
def test_permission_revocation_takes_effect_for_existing_login(game, revocation):
    api, sid, mid, ids = game
    user = make_user_session(api, ids[0])
    with SessionLocal() as db:
        if revocation == "attendance":
            row = db.scalar(select(SessionMember).where(SessionMember.session_id == sid,
                                                       SessionMember.member_id == ids[0]))
            row.attendance_status = "ABSENT"
        elif revocation == "unlink":
            db.delete(db.scalar(select(MemberAccountLink).where(MemberAccountLink.user_id == user.user_id)))
        else:
            member = db.get(Member, ids[0])
            if revocation == "inactive":
                member.active_yn = False
            else:
                member.deleted_at = utcnow()
        db.commit()
    assert _request(api, "POST", f"/matches/{mid}/pause", user.headers).status_code == 403
    assert api.ok(api.post(f"/matches/{mid}/pause"))["status"] == "PAUSED"


def test_disabled_account_cannot_reuse_login_cookie(game):
    api, _, mid, ids = game
    user = make_user_session(api, ids[0])
    with SessionLocal() as db:
        db.get(AppUser, user.user_id).active_yn = False
        db.commit()
    assert _request(api, "POST", f"/matches/{mid}/pause", user.headers).status_code == 401


def test_member_actions_keep_user_identity_and_admin_actions_remain_separate(game):
    api, _, mid, ids = game
    user = make_user_session(api, ids[0])
    api.ok(_request(api, "POST", f"/matches/{mid}/pause", user.headers))
    api.ok(api.post(f"/matches/{mid}/resume"))
    detail = api.ok(api.get(f"/matches/{mid}"))
    team = detail["teamA"]
    body = {"teamId": team["sessionTeamId"], "scorerMemberId": team["members"][0]["memberId"]}
    goal = api.ok(_request(api, "POST", f"/matches/{mid}/goals", user.headers, body))
    api.ok(_request(api, "POST", f"/matches/{mid}/events/{goal['eventId']}/cancel", user.headers))
    with SessionLocal() as db:
        events = list(db.scalars(select(MatchEvent).where(MatchEvent.match_id == mid)))
        member_events = [e for e in events if e.event_type in ("PAUSE", "GOAL", "GOAL_CANCEL")]
        assert len(member_events) == 3
        assert all(e.user_id == user.user_id and e.admin_id is None for e in member_events)
        admin_events = [e for e in events if e.event_type in ("START", "RESUME")]
        assert len(admin_events) == 2
        assert all(e.user_id is None and e.admin_id is not None for e in admin_events)
    # 공개 타임라인에 카카오 식별자/인증 계정 ID는 내보내지 않는다.
    for event in api.ok(_request(api, "GET", f"/matches/{mid}"))["events"]:
        assert "userId" not in event and "kakaoId" not in event
