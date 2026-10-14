"""코드 리뷰에서 나온 결함 재발 방지."""


def _setup(api, n=4, date="2026-11-14", teams=2):
    ids = [api.ok(api.post("/members", {"name": f"X{i}"}), 201)["memberId"] for i in range(n)]
    sid = api.ok(api.post("/sessions", {"sessionDate": date}), 201)["sessionId"]
    api.ok(api.post(f"/sessions/{sid}/members", {"memberIds": ids}))
    gen = api.ok(api.post(f"/sessions/{sid}/teams/generate", {"teamCount": teams, "seed": 5}))
    conf = api.ok(api.post(f"/sessions/{sid}/teams/confirm", {"generationId": gen["generationId"]}))
    return ids, sid, conf


def _match(api, sid, goal_a=True):
    m = api.next_match(sid)
    mid = m["matchId"]
    api.ok(api.post(f"/matches/{mid}/start"))
    d = api.ok(api.get(f"/matches/{mid}"))
    if goal_a:
        api.ok(api.post(f"/matches/{mid}/goals", {"teamId": m["teamA"]["sessionTeamId"],
                                                  "scorerMemberId": d["teamA"]["members"][0]["memberId"]}))
    return mid, m, d


def test_incremental_equals_full_with_one_sided_match(make_club):
    api = make_club("reg1")
    _, sid, _ = _setup(api)
    mid, m, d = _match(api, sid, goal_a=False)
    for x in d["teamB"]["members"]:  # 한쪽 팀 출전자가 0명인 경기 → Rating 재생에서 제외
        api.ok(api.delete(f"/matches/{mid}/members/{x['memberId']}"))
    api.ok(api.post(f"/matches/{mid}/end"))
    api.ok(api.post(f"/matches/{mid}/finalize"))
    for _ in range(2):
        mid2, _, _ = _match(api, sid)
        api.ok(api.post(f"/matches/{mid2}/end"))
        api.ok(api.post(f"/matches/{mid2}/finalize"))
    inc = {r["memberId"]: (r["rating"], r["matchCount"]) for r in api.ok(api.get("/admin/ratings"))}
    api.ok(api.post("/admin/rebuild"))
    full = {r["memberId"]: (r["rating"], r["matchCount"]) for r in api.ok(api.get("/admin/ratings"))}
    assert inc == full


def test_config_version_increments_each_change(make_club):
    api = make_club("reg2")
    v1 = api.ok(api.patch("/admin/config", {"values": {"MATCH_RATING_K": 24}}))["configVersion"]
    v2 = api.ok(api.patch("/admin/config", {"values": {"MATCH_RATING_K": 28}}))["configVersion"]
    assert v2 == v1 + 1
    assert [h["configVersion"] for h in api.ok(api.get("/admin/config/history"))] == [v2, v1]


def test_no_session_before_closed_and_scorer_team_lock(make_club):
    api = make_club("reg3")
    ids, sid, conf = _setup(api, date="2026-11-21")
    mid, m, d = _match(api, sid)
    scorer = d["teamA"]["members"][0]["memberId"]
    # 골 기록이 있는 선수를 상대 팀으로 옮길 수 없다
    r = api.post(f"/matches/{mid}/members", {"memberId": scorer, "teamId": m["teamB"]["sessionTeamId"]})
    assert r.status_code == 409 and r.json()["error"]["code"] == "MEMBER_HAS_EVENTS"
    api.ok(api.post(f"/matches/{mid}/end"))
    # 팀 제외(REMOVE) → 참석자 목록에서도 빠짐
    leaver = d["teamB"]["members"][0]["memberId"]
    s = api.ok(api.post(f"/sessions/{sid}/teams/assignments", {"action": "REMOVE", "memberId": leaver}))
    assert leaver not in [a["memberId"] for a in s["attendees"]]
    api.ok(api.post(f"/sessions/{sid}/close"))
    # 마감된 일정보다 앞선 날짜의 일정은 만들 수 없다(마감 구간 Rating 보호), 같은 날짜는 가능
    r = api.post("/sessions", {"sessionDate": "2026-11-20"})
    assert r.status_code == 409 and r.json()["error"]["code"] == "BEFORE_CLOSED_SESSION"
    api.ok(api.post("/sessions", {"sessionDate": "2026-11-21"}), 201)
