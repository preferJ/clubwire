"""프론트 화면용 조회 API: LIVE 배너, 일정 목록 인원수, 일정 요약, 멤버별 수상 이력."""


def test_live_summary_and_awards(make_club):
    api = make_club("front")
    ids = [api.ok(api.post("/members", {"name": f"F{i}"}), 201)["memberId"] for i in range(6)]
    sid = api.ok(api.post("/sessions", {"sessionDate": "2026-12-12"}), 201)["sessionId"]
    api.ok(api.post(f"/sessions/{sid}/members", {"memberIds": ids}))
    api.ok(api.post(f"/sessions/{sid}/guests", {"count": 1}))
    lst = api.ok(api.get("/sessions", admin=False))
    assert lst[0]["attendeeCount"] == 6 and lst[0]["guestCount"] == 1

    gen = api.ok(api.post(f"/sessions/{sid}/teams/generate", {"teamCount": 2}))
    api.ok(api.post(f"/sessions/{sid}/teams/confirm", {"generationId": gen["generationId"]}))
    m = api.next_match(sid)
    mid = m["matchId"]
    api.ok(api.post(f"/matches/{mid}/start"))
    live = api.ok(api.get("/live", admin=False))
    assert [x["matchId"] for x in live] == [mid] and live[0]["status"] == "RUNNING"

    d = api.ok(api.get(f"/matches/{mid}"))
    scorer = d["teamA"]["members"][0]["memberId"]
    api.ok(api.post(f"/matches/{mid}/goals", {"teamId": m["teamA"]["sessionTeamId"], "scorerMemberId": scorer}))
    api.ok(api.post(f"/matches/{mid}/end"))
    assert api.ok(api.get("/live", admin=False)) == []

    s = api.ok(api.get(f"/sessions/{sid}/summary", admin=False))
    assert s["finishedCount"] == 1 and s["unfinalizedCount"] == 1 and s["totalGoals"] == 1
    assert s["topScorers"][0]["memberId"] == scorer
    rec = {r["sessionTeamId"]: r for r in s["teamRecords"]}
    assert rec[m["teamA"]["sessionTeamId"]]["wins"] == 1

    api.ok(api.post("/titles/awards", {"titleCode": "MVP", "memberId": scorer, "sessionId": sid}), 201)
    mine = api.ok(api.get("/titles/awards", params={"memberId": scorer}, admin=False))
    assert mine[0]["titleCode"] == "MVP" and mine[0]["memberName"] == "F" + str(ids.index(scorer))
