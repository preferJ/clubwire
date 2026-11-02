"""일반 회원 경기 중 골 · 도움 기록 + 골 수정(취소 표시 + 새 기록) — DECISIONS 3-16."""
from sqlalchemy import select

from app.core.database import SessionLocal
from app.models import MatchEvent


def _setup(api, n=6, date="2026-12-05"):
    ids = [api.ok(api.post("/members", {"name": f"G{i}"}), 201)["memberId"] for i in range(n)]
    sid = api.ok(api.post("/sessions", {"sessionDate": date}), 201)["sessionId"]
    api.ok(api.post(f"/sessions/{sid}/members", {"memberIds": ids}))
    gen = api.ok(api.post(f"/sessions/{sid}/teams/generate", {"teamCount": 2, "seed": 3}))
    api.ok(api.post(f"/sessions/{sid}/teams/confirm", {"generationId": gen["generationId"]}))
    m = api.next_match(sid)
    return sid, m["matchId"]


def _detail(api, mid):
    return api.ok(api.get(f"/matches/{mid}", admin=False))


def _goal(api, mid, team, scorer, assist=None, admin=True, **extra):
    body = {"teamId": team["sessionTeamId"], "scorerMemberId": scorer, "assistMemberId": assist, **extra}
    return api.post(f"/matches/{mid}/goals", body, admin=admin)


def _goals(d):
    return [e for e in d["events"] if e["eventType"] == "GOAL"]


def test_member_can_record_goal_and_assist_only_while_match_is_live(make_club):
    api = make_club("mgoal1")
    _, mid = _setup(api)

    # 시작 전: 관리자와 똑같이 상태 오류(출전 명단은 시작할 때 만들어진다)
    r = _goal(api, mid, _detail(api, mid)["teamA"], None, admin=False)
    assert r.status_code == 409 and r.json()["error"]["code"] == "INVALID_MATCH_STATUS"

    api.ok(api.post(f"/matches/{mid}/start"))
    d = _detail(api, mid)
    a = d["teamA"]
    scorer, helper = a["members"][0]["memberId"], a["members"][1]["memberId"]
    res = api.ok(_goal(api, mid, a, scorer, helper, admin=False, idempotencyKey="member-1"))
    assert res["match"]["teamA"]["score"] == 1
    # 멱등키 재요청은 중복 기록 없이 그대로
    again = api.ok(_goal(api, mid, a, scorer, helper, admin=False, idempotencyKey="member-1"))
    assert again["duplicate"] is True and again["eventId"] == res["eventId"]

    # 일반 회원 기록은 처리 관리자 없음(NULL)
    with SessionLocal() as s:
        ev = s.scalar(select(MatchEvent).where(MatchEvent.event_id == res["eventId"]))
        assert ev.admin_id is None and ev.assist_member_id == helper

    # 일시정지 중에도 가능
    api.ok(api.post(f"/matches/{mid}/pause"))
    api.ok(_goal(api, mid, a, helper, admin=False))
    assert _detail(api, mid)["teamA"]["score"] == 2

    # 검증 규칙은 그대로: 상대 팀 선수를 득점자로 고를 수 없다
    b = d["teamB"]
    r = _goal(api, mid, a, b["members"][0]["memberId"], admin=False)
    assert r.status_code == 400 and r.json()["error"]["code"] == "INVALID_SCORER"

    # 경기가 끝나면 골 추가는 관리자만
    api.ok(api.post(f"/matches/{mid}/end"))
    r = _goal(api, mid, a, scorer, admin=False)
    assert r.status_code == 403 and r.json()["error"]["code"] == "ADMIN_REQUIRED_AFTER_END"
    api.ok(_goal(api, mid, a, scorer, elapsedSec=0))


def test_member_cannot_edit_cancel_or_control_match(make_club):
    api = make_club("mgoal2")
    _, mid = _setup(api, date="2026-12-06")
    api.ok(api.post(f"/matches/{mid}/start"))
    d = _detail(api, mid)
    eid = api.ok(_goal(api, mid, d["teamA"], d["teamA"]["members"][0]["memberId"], admin=False))["eventId"]
    body = {"teamId": d["teamA"]["sessionTeamId"], "scorerMemberId": d["teamA"]["members"][1]["memberId"]}
    assert api.patch(f"/matches/{mid}/events/{eid}", body, admin=False).status_code == 401
    assert api.post(f"/matches/{mid}/events/{eid}/cancel", admin=False).status_code == 401
    for action in ("pause", "end", "finalize"):
        assert api.post(f"/matches/{mid}/{action}", admin=False).status_code == 401


def test_edit_goal_keeps_history_and_moves_score(make_club):
    api = make_club("mgoal3")
    _, mid = _setup(api, date="2026-12-07")
    api.ok(api.post(f"/matches/{mid}/start"))
    d = _detail(api, mid)
    a, b = d["teamA"], d["teamB"]
    a0, a1, a2 = (x["memberId"] for x in a["members"][:3])
    b0 = b["members"][0]["memberId"]
    eid = api.ok(_goal(api, mid, a, a0, a1))["eventId"]
    elapsed = next(e for e in _goals(_detail(api, mid)) if e["eventId"] == eid)["elapsedSec"]

    # 득점자 · 도움 수정: 같은 팀이면 점수 그대로, 원래 시각 유지
    res = api.ok(api.patch(f"/matches/{mid}/events/{eid}",
                           {"teamId": a["sessionTeamId"], "scorerMemberId": a1, "assistMemberId": a2}))
    assert res["changed"] is True and res["eventId"] != eid
    assert (res["match"]["teamA"]["score"], res["match"]["teamB"]["score"]) == (1, 0)
    goals = {e["eventId"]: e for e in _goals(_detail(api, mid))}
    assert goals[eid]["cancelled"] is True
    new = goals[res["eventId"]]
    assert new["refEventId"] == eid and new["cancelled"] is False and new["elapsedSec"] == elapsed
    assert (new["scorerMemberId"], new["assistMemberId"]) == (a1, a2)
    # 취소 이벤트(GOAL_CANCEL)는 만들지 않는다(타임라인에 '골 취소'가 끼지 않게)
    assert not [e for e in _detail(api, mid)["events"] if e["eventType"] == "GOAL_CANCEL"]

    # 같은 수정이 다시 오면(더블클릭) 새로 만들지 않고 이미 고친 골을 돌려준다
    dup = api.ok(api.patch(f"/matches/{mid}/events/{eid}",
                           {"teamId": a["sessionTeamId"], "scorerMemberId": a1, "assistMemberId": a2}))
    assert dup["changed"] is False and dup["eventId"] == res["eventId"]
    # 다른 내용으로 이미 고친 골을 또 고치려 하면 409
    r = api.patch(f"/matches/{mid}/events/{eid}", {"teamId": a["sessionTeamId"], "scorerMemberId": a2})
    assert r.status_code == 409 and r.json()["error"]["code"] == "ALREADY_CANCELLED"

    # 바뀐 게 없으면 그대로
    same = api.ok(api.patch(f"/matches/{mid}/events/{res['eventId']}",
                            {"teamId": a["sessionTeamId"], "scorerMemberId": a1, "assistMemberId": a2}))
    assert same["changed"] is False and same["eventId"] == res["eventId"]

    # 득점 팀 변경(B팀 골로): 점수가 옮겨 간다
    moved = api.ok(api.patch(f"/matches/{mid}/events/{res['eventId']}",
                             {"teamId": b["sessionTeamId"], "scorerMemberId": b0}))
    assert (moved["match"]["teamA"]["score"], moved["match"]["teamB"]["score"]) == (0, 1)

    # 자책골로 바꾸면 도움은 비운다(A팀 a0의 자책 → B팀 점수)
    own = api.ok(api.patch(f"/matches/{mid}/events/{moved['eventId']}",
                           {"teamId": b["sessionTeamId"], "scorerMemberId": a0, "ownGoal": True,
                            "assistMemberId": a1}))
    ev = next(e for e in _goals(_detail(api, mid)) if e["eventId"] == own["eventId"])
    assert ev["ownGoal"] is True and ev["assistMemberId"] is None
    assert (own["match"]["teamA"]["score"], own["match"]["teamB"]["score"]) == (0, 1)

    # 검증 규칙은 등록과 같다
    r = api.patch(f"/matches/{mid}/events/{own['eventId']}", {"teamId": a["sessionTeamId"], "scorerMemberId": b0})
    assert r.status_code == 400 and r.json()["error"]["code"] == "INVALID_SCORER"


def test_edit_goal_time_after_end_then_stats_follow_edit(make_club):
    api = make_club("mgoal4")
    _, mid = _setup(api, date="2026-12-08")
    api.ok(api.post(f"/matches/{mid}/start"))
    d = _detail(api, mid)
    a = d["teamA"]
    a0, a1 = a["members"][0]["memberId"], a["members"][1]["memberId"]
    eid = api.ok(_goal(api, mid, a, a0))["eventId"]
    api.ok(api.post(f"/matches/{mid}/end"))

    # 끝난 뒤에는 득점 시각도 고칠 수 있다(진행 시간 밖이면 400)
    r = api.patch(f"/matches/{mid}/events/{eid}", {"teamId": a["sessionTeamId"], "scorerMemberId": a1,
                                                    "elapsedSec": 99999})
    assert r.status_code == 400
    res = api.ok(api.patch(f"/matches/{mid}/events/{eid}", {"teamId": a["sessionTeamId"], "scorerMemberId": a1,
                                                             "elapsedSec": 0}))
    assert next(e for e in _goals(_detail(api, mid)) if e["eventId"] == res["eventId"])["elapsedSec"] == 0

    # 확정하면 고친 기록만 개인 기록에 반영
    api.ok(api.post(f"/matches/{mid}/finalize"))
    stats = {x["memberId"]: x for x in api.ok(api.get("/stats/members", admin=False))}
    assert stats[a1]["goals"] == 1 and stats[a0]["goals"] == 0

    # 확정 뒤 수정 불가
    r = api.patch(f"/matches/{mid}/events/{res['eventId']}", {"teamId": a["sessionTeamId"], "scorerMemberId": a0})
    assert r.status_code == 409 and r.json()["error"]["code"] == "MATCH_FINALIZED"


def test_edit_cancelled_goal_or_unknown_event(make_club):
    api = make_club("mgoal5")
    _, mid = _setup(api, date="2026-12-09")
    api.ok(api.post(f"/matches/{mid}/start"))
    d = _detail(api, mid)
    a = d["teamA"]
    eid = api.ok(_goal(api, mid, a, a["members"][0]["memberId"]))["eventId"]
    api.ok(api.post(f"/matches/{mid}/events/{eid}/cancel"))
    body = {"teamId": a["sessionTeamId"], "scorerMemberId": a["members"][1]["memberId"]}
    r = api.patch(f"/matches/{mid}/events/{eid}", body)
    assert r.status_code == 409 and r.json()["error"]["code"] == "ALREADY_CANCELLED"
    start_event = next(e for e in _detail(api, mid)["events"] if e["eventType"] == "START")["eventId"]
    assert api.patch(f"/matches/{mid}/events/{start_event}", body).status_code == 404
    assert api.patch(f"/matches/{mid}/events/999999", body).status_code == 404
