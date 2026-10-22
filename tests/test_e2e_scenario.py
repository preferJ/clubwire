"""§106 Backend 개발 완료 기준 시나리오(+ 이번 결정사항) 처음부터 끝까지."""
from datetime import date, timedelta

from sqlalchemy import func, select, update

from app.models import MatchEvent, MatchGame, PlayerRatingHistory
from app.services.match_service import auto_end_due_matches


def _members(api, n):
    return [api.ok(api.post("/members", {"name": f"선수{i:02d}"}), 201)["memberId"] for i in range(1, n + 1)]


def _confirm(api, sid, team_count, seed=1):
    gen = api.ok(api.post(f"/sessions/{sid}/teams/generate", {"teamCount": team_count, "seed": seed}))
    return api.ok(api.post(f"/sessions/{sid}/teams/confirm", {"generationId": gen["generationId"]})), gen


def _play(api, sid, goals_a=1, goals_b=0, teams=None, finalize=True):
    m = api.next_match(sid, teams)
    mid = m["matchId"]
    api.ok(api.post(f"/matches/{mid}/start"))
    detail = api.ok(api.get(f"/matches/{mid}"))
    a_members = [x["memberId"] for x in detail["teamA"]["members"]]
    b_members = [x["memberId"] for x in detail["teamB"]["members"]]
    for _ in range(goals_a):
        api.ok(api.post(f"/matches/{mid}/goals", {"teamId": m["teamA"]["sessionTeamId"], "scorerMemberId": a_members[0]}))
    for _ in range(goals_b):
        api.ok(api.post(f"/matches/{mid}/goals", {"teamId": m["teamB"]["sessionTeamId"], "scorerMemberId": b_members[0]}))
    api.ok(api.post(f"/matches/{mid}/end"))
    if finalize:
        api.ok(api.post(f"/matches/{mid}/finalize"))
    return m, a_members, b_members


def test_full_loop(make_club, client, db):
    api = make_club("e2e")

    # --- 관리자 모드
    assert api.post("/admin/auth", {"password": "0000"}, admin=False).status_code == 401
    assert api.post("/members", {"name": "x"}, admin=False).status_code == 401
    assert api.ok(api.get("", admin=True))["isAdmin"] is True
    assert api.ok(api.get("", admin=False))["isAdmin"] is False

    # --- 1~4. Member 18명 / Session / 18명 참석
    ids = _members(api, 18)
    s = api.ok(api.post("/sessions", {"sessionDate": "2026-10-17", "title": "토요 정기"}), 201)
    sid = s["sessionId"]
    api.ok(api.post(f"/sessions/{sid}/members", {"memberIds": ids}))

    # --- 5~6. 3팀 자동 편성 → 6:6:6 → [일정확정]
    confirmed, gen = _confirm(api, sid, 3)
    assert sorted(t["headcount"] for t in gen["teams"]) == [6, 6, 6]
    assert confirmed["status"] == "CONFIRMED"
    teams = {t["teamCode"]: t["sessionTeamId"] for t in confirmed["teams"]}
    # 공개 조회에는 Rating이 없다
    pub = api.ok(api.get(f"/sessions/{sid}", admin=False))
    assert "ratingSnapshot" not in pub["teams"][0]["members"][0]
    # 관리자에게도 선수별 Rating은 없다(팀 단위 편성 정보만)
    adm = api.ok(api.get(f"/sessions/{sid}"))
    assert not {"ratingSnapshot", "confidenceSnapshot"} & set(adm["teams"][0]["members"][0])
    assert "avgRatingSnapshot" in adm["teams"][0]
    assert all(set(m) == {"memberId", "name"} for t in gen["teams"] for m in t["members"])
    # PRE_MATCH 기사 1건 생성(게시 방식 MANUAL → GENERATED)
    pre = api.ok(api.get("/articles", params={"all": "true", "sessionId": sid}))
    assert len(pre) == 1 and pre[0]["articleType"] == "PRE_MATCH" and pre[0]["status"] == "GENERATED"
    assert api.ok(api.get("/articles", admin=False)) == []  # 게시 전엔 공개 목록에 없음
    api.ok(api.post(f"/articles/{pre[0]['articleId']}/publish"))
    assert len(api.ok(api.get("/articles", admin=False))) == 1

    # --- 7~13. A vs B 시작 / 타이머 / 골 / 도움 / 골 취소 / 종료 / 확정
    sug = api.ok(api.get(f"/sessions/{sid}/matches/next-suggestion"))
    assert (sug["suggestedTeamAId"], sug["suggestedTeamBId"]) == (teams["A"], teams["B"])
    m1 = api.next_match(sid, (teams["A"], teams["B"]))
    mid = m1["matchId"]
    r = api.post(f"/sessions/{sid}/matches/next", {"teamAId": teams["A"], "teamBId": teams["C"]})
    assert r.status_code == 409  # 대기 경기 있음
    st = api.ok(api.post(f"/matches/{mid}/start"))
    assert st["status"] == "RUNNING" and st["remainingSec"] <= 600
    d = api.ok(api.get(f"/matches/{mid}", admin=False))
    a_ids = [x["memberId"] for x in d["teamA"]["members"]]
    b_ids = [x["memberId"] for x in d["teamB"]["members"]]
    assert len(a_ids) == 6 and len(b_ids) == 6

    g1 = api.ok(api.post(f"/matches/{mid}/goals", {"teamId": teams["A"], "scorerMemberId": a_ids[0],
                                                   "assistMemberId": a_ids[1], "idempotencyKey": "k1"}))
    dup = api.ok(api.post(f"/matches/{mid}/goals", {"teamId": teams["A"], "scorerMemberId": a_ids[0],
                                                    "assistMemberId": a_ids[1], "idempotencyKey": "k1"}))
    assert dup["duplicate"] is True and dup["eventId"] == g1["eventId"] and dup["match"]["teamA"]["score"] == 1
    # 검증: 도움=득점자, 상대팀 득점자
    assert api.post(f"/matches/{mid}/goals", {"teamId": teams["A"], "scorerMemberId": a_ids[0],
                                              "assistMemberId": a_ids[0]}).status_code == 400
    assert api.post(f"/matches/{mid}/goals", {"teamId": teams["A"], "scorerMemberId": b_ids[0]}).status_code == 400
    gb = api.ok(api.post(f"/matches/{mid}/goals", {"teamId": teams["B"], "scorerMemberId": b_ids[0]}))
    assert gb["match"]["teamB"]["score"] == 1
    api.ok(api.post(f"/matches/{mid}/pause"))
    api.ok(api.post(f"/matches/{mid}/resume"))
    c = api.ok(api.post(f"/matches/{mid}/events/{gb['eventId']}/cancel", {"memo": "오프사이드"}))
    assert c["match"]["teamB"]["score"] == 0
    assert api.post(f"/matches/{mid}/events/{gb['eventId']}/cancel").status_code == 409
    # 자책골: B 선수가 자책 → A 득점
    og = api.ok(api.post(f"/matches/{mid}/goals", {"teamId": teams["A"], "scorerMemberId": b_ids[1], "ownGoal": True}))
    assert og["match"]["teamA"]["score"] == 2
    api.ok(api.post(f"/matches/{mid}/end"))
    # 점수 = 유효 골 이벤트 수
    goals = db.scalar(select(func.count()).select_from(MatchEvent).where(
        MatchEvent.match_id == mid, MatchEvent.event_type == "GOAL", MatchEvent.cancelled_yn.is_(False)))
    assert goals == 2

    fin = api.ok(api.post(f"/matches/{mid}/finalize"))
    assert fin["finalized"] and fin["winTeamId"] == teams["A"]
    assert api.post(f"/matches/{mid}/finalize").status_code == 409  # 멱등

    # --- 14~17. 통계 / Pair / Rating / Rating History
    stats = {x["memberId"]: x for x in api.ok(api.get("/stats/members", admin=False))}
    assert stats[a_ids[0]]["goals"] == 1 and stats[a_ids[1]]["assists"] == 1 and stats[b_ids[1]]["ownGoals"] == 1
    assert stats[a_ids[0]]["wins"] == 1 and stats[b_ids[0]]["losses"] == 1
    h2h = api.ok(api.get("/stats/pairs", params={"memberA": a_ids[0], "memberB": b_ids[0]}, admin=False))
    assert h2h["opponentMatches"] == 1 and h2h["winsA"] == 1
    ratings = {x["memberId"]: x for x in api.ratings_db()}
    assert ratings[a_ids[0]]["rating"] > 1000 > ratings[b_ids[0]]["rating"]
    c_member = next(i for i in ids if i not in a_ids + b_ids)
    assert ratings[c_member]["rating"] == 1000  # 대기팀은 영향 없음
    hist = api.rating_history_db(a_ids[0])
    assert len(hist) == 1 and hist[0]["reason"] == "MATCH_RESULT" and hist[0]["referenceId"] == mid
    # Rating은 관리자에게도 API로 공개하지 않는다(DB에서만 확인)
    assert api.get("/admin/ratings").status_code == 404
    assert api.get(f"/admin/ratings/{a_ids[0]}/history").status_code == 404

    # --- 대진은 매 경기 관리자가 지정(추천은 가장 오래 쉰 두 팀)
    assert api.post(f"/sessions/{sid}/matches/next", {}).status_code == 422
    assert api.post(f"/sessions/{sid}/matches/next", {"teamAId": teams["A"], "teamBId": teams["A"]}).status_code == 400
    sug = api.ok(api.get(f"/sessions/{sid}/matches/next-suggestion"))
    assert (sug["suggestedTeamAId"], sug["suggestedTeamBId"]) == (teams["C"], teams["A"])
    assert {t["teamCode"]: t["consecutive"] for t in sug["teams"]} == {"A": 1, "B": 1, "C": 0}
    m2, _, _ = _play(api, sid, 0, 2, teams=(teams["A"], teams["C"]))  # 관리자가 A vs C 지정, C 승
    m3, _, _ = _play(api, sid, 1, 1, finalize=False)  # 추천(B vs C) 그대로, 무승부, 확정 안 함
    assert {m3["teamA"]["sessionTeamId"], m3["teamB"]["sessionTeamId"]} == {teams["B"], teams["C"]}
    # 수동 MVP 수여
    api.ok(api.post("/titles/awards", {"titleCode": "MVP", "memberId": a_ids[0], "sessionId": sid}), 201)

    # --- [일정마감]: 미확정 경기 자동 확정 → 자동 타이틀 → 마감 기사
    closed = api.ok(api.post(f"/sessions/{sid}/close"))
    assert closed["status"] == "CLOSED" and len(closed["articleIds"]) == 1
    assert all(x["finalized"] for x in closed["matches"])
    recap = api.ok(api.get(f"/articles/{closed['articleIds'][0]}"))
    assert recap["articleType"] == "SESSION_RECAP" and recap["status"] == "GENERATED" and "마감" in recap["tags"]
    awards = api.ok(api.get("/titles/awards", admin=False))
    codes = {a["titleCode"] for a in awards}
    assert {"MVP", "TOP_SCORER"} <= codes
    assert api.ok(api.get("/stats/members", admin=False))[0] is not None
    assert {x["memberId"]: x for x in api.ok(api.get("/stats/members"))}[a_ids[0]]["mvpCount"] == 1
    insights = api.ok(api.get("/admin/insights", params={"sessionId": sid}))
    assert any(i["phase"] == "POST" for i in insights)
    # 마감 후 수정 불가
    r = api.post(f"/matches/{mid}/goals", {"teamId": teams["A"], "scorerMemberId": a_ids[0]})
    assert r.status_code == 409 and r.json()["error"]["code"] == "SESSION_CLOSED"
    assert api.post(f"/matches/{mid}/unfinalize").status_code == 409


def test_guests_rotation_timer_correction_and_ws(make_club, client, db):
    api = make_club("live")
    ids = _members(api, 11)
    sid = api.ok(api.post("/sessions", {"sessionDate": "2026-10-24"}), 201)["sessionId"]
    api.ok(api.post(f"/sessions/{sid}/members", {"memberIds": ids}))
    api.ok(api.post(f"/sessions/{sid}/guests", {"count": 2}))
    confirmed, gen = _confirm(api, sid, 2)
    assert sorted(t["headcount"] for t in gen["teams"]) == [6, 7]  # 13명 → 6:7, 게스트 포함
    assert all(len(t["guests"]) == 1 for t in gen["teams"])  # 게스트는 분산
    teams = {t["teamCode"]: t["sessionTeamId"] for t in confirmed["teams"]}

    # 지각 멤버 추가(수동 변경 + 이력)
    late = api.ok(api.post("/members", {"name": "지각생"}), 201)["memberId"]
    api.ok(api.post(f"/sessions/{sid}/teams/assignments", {"action": "ADD", "memberId": late, "toTeamId": teams["A"],
                                                          "reason": "지각"}))
    logs = api.ok(api.get(f"/sessions/{sid}/teams/assignments"))
    assert logs[0]["action"] == "ADD"

    # WebSocket 구독(누구나) → 경기 시작/골 브로드캐스트 수신
    with client.websocket_connect("/ws/clubs/live") as ws:
        assert ws.receive_json()["type"] == "HELLO"
        m = api.next_match(sid)
        assert ws.receive_json()["type"] == "MATCH_UPDATED"
        mid = m["matchId"]
        api.ok(api.post(f"/matches/{mid}/start"))
        msgs = [ws.receive_json() for _ in range(2)]
        assert {x["type"] for x in msgs} >= {"MATCH_UPDATED"}
        g = api.ok(api.post(f"/matches/{mid}/goals", {"teamId": teams["A"], "guestGoal": True}))
        types = [ws.receive_json()["type"] for _ in range(2)]
        assert types == ["MATCH_EVENT", "MATCH_UPDATED"]
        assert g["match"]["teamA"]["score"] == 1
        ws.send_text("ping")
        assert ws.receive_json()["type"] == "PONG"

    d = api.ok(api.get(f"/matches/{mid}"))
    assert late in [x["memberId"] for x in d["teamA"]["members"]]  # 지각생이 출전 명단에 포함

    # 타이머 자동 종료: 시작 시각을 과거로 돌려 시간 초과 상황 재현
    started = db.scalar(select(MatchGame.started_at).where(MatchGame.match_id == mid))
    db.execute(update(MatchGame).where(MatchGame.match_id == mid).values(started_at=started - timedelta(seconds=700)))
    db.commit()
    assert auto_end_due_matches() == 1
    d = api.ok(api.get(f"/matches/{mid}"))
    assert d["status"] == "FINISHED" and d["endReason"] == "TIME_UP" and d["remainingSec"] == 0

    api.ok(api.post(f"/matches/{mid}/finalize"))
    a_member = d["teamA"]["members"][0]["memberId"]
    before = api.ratings_db()

    # 2팀 → 항상 같은 대진
    m2, a2, b2 = _play(api, sid, 0, 1)
    assert {m2["teamA"]["sessionTeamId"], m2["teamB"]["sessionTeamId"]} == set(teams.values())

    # 확정 경기 정정: 1경기 확정 해제 → 득점 정정 → 재확정 → 이후 경기 Rating 재계산
    assert api.post(f"/matches/{mid}/goals", {"teamId": teams["B"], "guestGoal": True}).status_code == 409
    api.ok(api.post(f"/matches/{mid}/unfinalize"))
    api.ok(api.post(f"/matches/{mid}/goals", {"teamId": teams["B"], "guestGoal": True, "elapsedSec": 300}))
    api.ok(api.post(f"/matches/{mid}/finalize"))
    voided = db.scalar(select(func.count()).select_from(PlayerRatingHistory).where(PlayerRatingHistory.voided_yn.is_(True)))
    assert voided > 0  # 기존 이력은 지우지 않고 VOIDED
    after = {x["memberId"]: x["rating"] for x in api.ratings_db()}
    assert after != {x["memberId"]: x["rating"] for x in before}
    # 전체 재계산 결과와 증분 재계산 결과가 같아야 한다
    api.ok(api.post("/admin/rebuild"))
    rebuilt = {x["memberId"]: x["rating"] for x in api.ratings_db()}
    assert rebuilt == after
    hist = api.rating_history_db(a_member)
    assert len(hist) == 2 and all(h["reason"] == "ADMIN_RECALC" for h in hist)


def test_insights_return_player_and_close_order(make_club, client):
    api = make_club("wire")
    api.ok(api.patch("/admin/config", {"values": {"ARTICLE_PUBLISH_MODE": "AUTO"}}))
    ids = _members(api, 8)
    d1 = date(2026, 8, 1)
    s1 = api.ok(api.post("/sessions", {"sessionDate": d1.isoformat()}), 201)["sessionId"]
    api.ok(api.post(f"/sessions/{s1}/members", {"memberIds": ids}))
    _confirm(api, s1, 2)
    for _ in range(3):
        _play(api, s1, 2, 0)
    # 나중 일정이 먼저 마감되려 하면 거부
    s2 = api.ok(api.post("/sessions", {"sessionDate": (d1 + timedelta(days=63)).isoformat()}), 201)["sessionId"]
    api.ok(api.post(f"/sessions/{s2}/members", {"memberIds": ids[:6]}))
    _confirm(api, s2, 2)
    r = api.post(f"/sessions/{s2}/close")
    assert r.status_code == 409 and r.json()["error"]["code"] == "PREVIOUS_SESSION_OPEN"
    api.ok(api.post(f"/sessions/{s1}/close"))

    # 63일 만의 복귀 → s2 PRE Insight에 RETURN_PLAYER
    pre = [i for i in api.ok(api.get("/admin/insights", params={"sessionId": s2})) if i["phase"] == "PRE"]
    ret = [i for i in pre if i["type"] == "RETURN_PLAYER"]
    assert len(ret) == 6 and ret[0]["facts"]["daysSinceLastAppearance"] == 63
    assert all("rating" not in str(i["facts"]).lower() for i in pre)
    # 연승 선수(3연승) Insight
    assert any(i["type"] == "WIN_STREAK" and i["facts"]["streak"] == 3 for i in pre)
    # AUTO 게시 모드 → 공개 목록에 바로 노출, 태그는 Backend 매핑
    arts = api.ok(api.get("/articles", admin=False))
    assert arts and all(a["status"] == "PUBLISHED" for a in arts)
    assert any("복귀" in a["tags"] for a in arts)
    # 기사 재생성 → 새 버전, 기존 보존
    aid = arts[0]["articleId"]
    new = api.ok(api.post(f"/articles/{aid}/regenerate"), 201)
    assert new["generationNo"] == 2 and new["parentArticleId"] in (aid, arts[0]["parentArticleId"])
    detail = api.ok(api.get(f"/articles/{new['articleId']}"))
    assert detail["status"] == "PUBLISHED"
    old = api.ok(api.get(f"/articles/{aid}"))
    assert old["status"] == "SUPERSEDED"
    # 설정 변경 이력
    hist = api.ok(api.get("/admin/config/history"))
    assert hist[0]["key"] == "ARTICLE_PUBLISH_MODE" and hist[0]["after"] == "AUTO"
