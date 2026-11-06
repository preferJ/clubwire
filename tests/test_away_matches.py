"""원정 경기(1팀 편성 + 원정팀) — DECISIONS 3-17.

- 원정팀은 목록(OPPONENT_TEAM)에서만 고르고, 없으면 [직접추가](같은 이름은 공백 · 대소문자 무시하고 기존 팀)
- 1팀 편성: 원정팀 필수, 확정하면 우리 팀(클럽 이름) + 원정팀(VS, 선수 없음)
- 경기마다 출전 선수 선택, 원정팀 골은 점수만, 자책골 규칙
- 원정 기록은 내부 기록 · 실력 점수 · 타이틀과 완전히 분리(별도 /stats/away, 상대별 상세 /stats/away/opponents/{id})
- [원정팀 관리]: 이름 수정(지난 원정 일정 표시도 새 이름) · 숨기기(목록에서만 빠짐, 전적 유지) · 복원
- 원정 프리뷰 · 마감 기사: 원정 태그, 사실마다 away 표시, 상대 전적(OPPONENT_RECORD)
"""
from sqlalchemy import select

from app.core.database import SessionLocal
from app.models import MemberTitle


def _opponent(api, name):
    r = api.post("/opponents", {"name": name})
    assert r.status_code in (200, 201), r.text
    return r.json()["opponentId"]


def _away_session(api, ids, date, opponent="한강FC"):
    sid = api.ok(api.post("/sessions", {"sessionDate": date}), 201)["sessionId"]
    api.ok(api.post(f"/sessions/{sid}/members", {"memberIds": ids}))
    gen = api.ok(api.post(f"/sessions/{sid}/teams/generate", {"teamCount": 1, "opponentId": _opponent(api, opponent)}))
    conf = api.ok(api.post(f"/sessions/{sid}/teams/confirm", {"generationId": gen["generationId"]}))
    ours = next(t for t in conf["teams"] if not t["opponent"])
    opp = next(t for t in conf["teams"] if t["opponent"])
    return sid, conf, ours, opp


def _members(api, n=6, prefix="W"):
    return [api.ok(api.post("/members", {"name": f"{prefix}{i}"}), 201)["memberId"] for i in range(n)]


def _match(api, sid, ours, opp, lineup):
    m = api.ok(api.post(f"/sessions/{sid}/matches/next", {"teamAId": ours["sessionTeamId"],
                                                         "teamBId": opp["sessionTeamId"], "memberIds": lineup}), 201)
    return m["matchId"]


def _goal(api, mid, team, scorer=None, assist=None, own=False, admin=True):
    return api.post(f"/matches/{mid}/goals", {"teamId": team["sessionTeamId"], "scorerMemberId": scorer,
                                              "assistMemberId": assist, "ownGoal": own}, admin=admin)


def test_one_team_generation_creates_our_team_and_opponent(make_club):
    api = make_club("away1")
    ids = _members(api)
    sid = api.ok(api.post("/sessions", {"sessionDate": "2027-01-09"}), 201)["sessionId"]
    api.ok(api.post(f"/sessions/{sid}/members", {"memberIds": ids}))
    # 원정팀은 목록에서만: 이름 직접 입력은 받지 않는다(422), 고르지 않으면 400, 없는 팀은 404
    r = api.post(f"/sessions/{sid}/teams/generate", {"teamCount": 1, "opponentName": "한강FC"})
    assert r.status_code == 422
    r = api.post(f"/sessions/{sid}/teams/generate", {"teamCount": 1})
    assert r.status_code == 400 and r.json()["error"]["code"] == "OPPONENT_REQUIRED"
    r = api.post(f"/sessions/{sid}/teams/generate", {"teamCount": 1, "opponentId": 999999})
    assert r.status_code == 404 and r.json()["error"]["code"] == "OPPONENT_NOT_FOUND"

    # [직접추가]: 관리자만, 같은 이름(공백 · 대소문자 무시)은 기존 팀을 돌려준다
    assert api.post("/opponents", {"name": "한강FC"}, admin=False).status_code == 401
    created = api.post("/opponents", {"name": " 한강FC "})
    assert created.status_code == 201 and created.json()["name"] == "한강FC"
    oid = created.json()["opponentId"]
    again = api.post("/opponents", {"name": "한강 fc"})
    assert again.status_code == 200 and again.json()["opponentId"] == oid
    assert api.ok(api.get("/opponents", admin=False)) == [{"opponentId": oid, "name": "한강FC", "active": True}]

    gen = api.ok(api.post(f"/sessions/{sid}/teams/generate", {"teamCount": 1, "opponentId": oid}))
    assert gen["teamCount"] == 1 and gen["opponentName"] == "한강FC" and gen["opponentId"] == oid
    assert len(gen["teams"]) == 1
    assert len(gen["teams"][0]["members"]) == 6 and gen["balanceLabel"] == "원정 경기"

    conf = api.ok(api.post(f"/sessions/{sid}/teams/confirm", {"generationId": gen["generationId"]}))
    assert conf["away"] is True and conf["opponentName"] == "한강FC" and conf["opponentId"] == oid and conf["teamCount"] == 1
    ours = next(t for t in conf["teams"] if not t["opponent"])
    opp = next(t for t in conf["teams"] if t["opponent"])
    assert ours["displayName"] == "away1 FC" and len(ours["members"]) == 6
    assert opp["teamCode"] == "VS" and opp["displayName"] == "한강FC" and opp["members"] == []

    # 프리뷰 기사: 원정 태그 + 원정 문맥 + 상대 전적(첫 맞대결)
    pre = api.ok(api.get("/articles", params={"all": "true", "sessionId": sid}))[0]
    detail = api.ok(api.get(f"/articles/{pre['articleId']}"))
    assert "원정" in detail["tags"] and "프리뷰" in detail["tags"]
    assert detail["requestJson"]["away"] == {"opponentName": "한강FC", "ourTeamName": "away1 FC"}
    assert [t.get("teamName") for t in detail["requestJson"]["teams"]] == ["away1 FC"]
    assert "한강FC" in detail["content"]
    insights = api.ok(api.get("/admin/insights", params={"sessionId": sid}))
    assert insights and all(i["facts"].get("away") is True for i in insights)
    opp_rec = next(i for i in insights if i["type"] == "OPPONENT_RECORD")
    assert opp_rec["facts"]["firstMeeting"] is True and opp_rec["facts"]["opponentName"] == "한강FC"

    # 원정팀으로는 지각 추가 · 이동 불가
    r = api.post(f"/sessions/{sid}/teams/assignments", {"action": "MOVE", "memberId": ids[0],
                                                       "toTeamId": opp["sessionTeamId"]})
    assert r.status_code == 400 and r.json()["error"]["code"] == "INVALID_TEAM"

    # 원정팀 바꾸기(원정 일정만, 목록에서)
    mapo = _opponent(api, "마포FC")
    s = api.ok(api.patch(f"/sessions/{sid}", {"opponentId": mapo}))
    assert s["opponentName"] == "마포FC" and next(t for t in s["teams"] if t["opponent"])["displayName"] == "마포FC"
    other = api.ok(api.post("/sessions", {"sessionDate": "2027-01-10"}), 201)["sessionId"]
    r = api.patch(f"/sessions/{other}", {"opponentId": mapo})
    assert r.status_code == 400 and r.json()["error"]["code"] == "NOT_AWAY_SESSION"


def test_lineup_per_match_and_opponent_goal_rules(make_club):
    api = make_club("away2")
    ids = _members(api)
    sid, _, ours, opp = _away_session(api, ids, "2027-01-16")

    sug = api.ok(api.get(f"/sessions/{sid}/matches/next-suggestion"))
    assert sug["away"] is True and sug["suggestedTeamAId"] == ours["sessionTeamId"]
    assert sug["suggestedTeamBId"] == opp["sessionTeamId"] and len(sug["roster"]) == 6 and sug["lineupMemberIds"] == []

    body = {"teamAId": opp["sessionTeamId"], "teamBId": ours["sessionTeamId"]}
    r = api.post(f"/sessions/{sid}/matches/next", body)
    assert r.status_code == 400 and r.json()["error"]["code"] == "LINEUP_REQUIRED"
    outsider = _members(api, 1, "Z")[0]
    r = api.post(f"/sessions/{sid}/matches/next", {**body, "memberIds": [ids[0], outsider]})
    assert r.status_code == 400 and r.json()["error"]["code"] == "INVALID_LINEUP"
    # 팀 순서를 바꿔 보내도 TEAM_A = 우리 팀으로 맞춘다
    m = api.ok(api.post(f"/sessions/{sid}/matches/next", {**body, "memberIds": ids[:4]}), 201)
    mid = m["matchId"]
    assert m["teamA"]["sessionTeamId"] == ours["sessionTeamId"] and m["teamB"]["opponent"] is True

    # 시작 전에도 출전 선수 고치기(우리 팀만)
    d = api.ok(api.get(f"/matches/{mid}", admin=False))
    assert sorted(x["memberId"] for x in d["teamA"]["members"]) == sorted(ids[:4]) and d["teamB"]["members"] == []
    api.ok(api.post(f"/matches/{mid}/members", {"memberId": ids[4], "teamId": ours["sessionTeamId"]}))
    r = api.post(f"/matches/{mid}/members", {"memberId": ids[5], "teamId": opp["sessionTeamId"]})
    assert r.status_code == 400 and r.json()["error"]["code"] == "INVALID_TEAM"
    api.ok(api.delete(f"/matches/{mid}/members/{ids[3]}"))

    api.ok(api.post(f"/matches/{mid}/start"))
    lineup = [ids[0], ids[1], ids[2], ids[4]]
    # 우리 골: 기존 방식(출전 선수 득점 + 도움)
    api.ok(_goal(api, mid, ours, ids[0], ids[1]))
    r = _goal(api, mid, ours, ids[3])  # 이번 경기 출전 선수가 아님
    assert r.status_code == 400 and r.json()["error"]["code"] == "INVALID_SCORER"
    # 원정팀 골: 점수만(일반 회원도)
    api.ok(_goal(api, mid, opp, admin=False))
    r = _goal(api, mid, opp, ids[0])
    assert r.status_code == 400 and r.json()["error"]["code"] == "INVALID_SCORER"
    # 우리 선수 자책골 = 원정팀 골 + 자책 선수 / 원정팀 자책골 = 우리 골, 득점자 없음
    api.ok(_goal(api, mid, opp, ids[2], own=True))
    api.ok(_goal(api, mid, ours, own=True))
    r = _goal(api, mid, ours, ids[1], own=True)
    assert r.status_code == 400
    res = api.ok(_goal(api, mid, ours, ids[4]))
    assert (res["match"]["teamA"]["score"], res["match"]["teamB"]["score"]) == (3, 2)

    # 원정팀 골 수정: 우리 골로 바꾸면 득점자 지정
    d = api.ok(api.get(f"/matches/{mid}", admin=False))
    opp_goal = next(e for e in d["events"] if e["eventType"] == "GOAL" and e["teamId"] == opp["sessionTeamId"]
                    and not e["ownGoal"])
    assert opp_goal["scorerMemberId"] is None
    fixed = api.ok(api.patch(f"/matches/{mid}/events/{opp_goal['eventId']}",
                             {"teamId": ours["sessionTeamId"], "scorerMemberId": ids[1]}))
    assert (fixed["match"]["teamA"]["score"], fixed["match"]["teamB"]["score"]) == (4, 1)
    api.ok(api.post(f"/matches/{mid}/end"))
    assert api.ok(api.get(f"/sessions/{sid}/matches/next-suggestion"))["lineupMemberIds"] == sorted(lineup)


def test_away_records_are_separate_from_internal(make_club):
    api = make_club("away3")
    ids = _members(api)
    before = {r["memberId"]: r["rating"] for r in api.ratings_db()}
    sid, _, ours, opp = _away_session(api, ids, "2027-01-23")
    m1 = _match(api, sid, ours, opp, ids[:5])
    api.ok(api.post(f"/matches/{m1}/start"))
    api.ok(_goal(api, m1, ours, ids[0], ids[1]))
    api.ok(_goal(api, m1, ours, ids[0]))
    api.ok(_goal(api, m1, opp))
    api.ok(api.post(f"/matches/{m1}/end"))
    api.ok(api.post(f"/matches/{m1}/finalize"))
    m2 = _match(api, sid, ours, opp, ids[1:4])
    api.ok(api.post(f"/matches/{m2}/start"))
    api.ok(_goal(api, m2, opp))
    api.ok(api.post(f"/matches/{m2}/end"))
    closed = api.ok(api.post(f"/sessions/{sid}/close"))
    assert closed["status"] == "CLOSED" and len(closed["articleIds"]) == 1

    # 실력 점수 · 개인 기록 · 타이틀 변화 없음
    assert {r["memberId"]: r["rating"] for r in api.ratings_db()} == before
    assert all(s["games"] == 0 and s["goals"] == 0 for s in api.ok(api.get("/stats/members", admin=False)))
    with SessionLocal() as s:
        assert not s.scalars(select(MemberTitle).where(MemberTitle.session_id == sid)).all()

    # 원정 기록은 따로
    away = api.ok(api.get("/stats/away", admin=False))
    assert away["summary"] == {"sessions": 1, "matches": 2, "wins": 1, "draws": 0, "losses": 1,
                               "goalsFor": 2, "goalsAgainst": 2}
    assert [o["opponentName"] for o in away["opponents"]] == ["한강FC"] and away["opponents"][0]["matches"] == 2
    top = away["members"][0]
    assert top["memberId"] == ids[0] and top["goals"] == 2 and top["games"] == 1 and top["wins"] == 1
    w1 = next(x for x in away["members"] if x["memberId"] == ids[1])
    assert (w1["games"], w1["wins"], w1["losses"], w1["assists"]) == (2, 1, 1, 1)
    detail = api.ok(api.get(f"/stats/members/{ids[1]}", admin=False))
    assert detail["summary"]["games"] == 0
    assert (detail["away"]["games"], detail["away"]["assists"]) == (2, 1)
    assert detail["away"]["recent"][0]["opponentName"] == "한강FC" and detail["away"]["recent"][0]["result"] == "L"

    # 마감 기사: 원정 결과 요약 + 원정 태그
    recap = api.ok(api.get(f"/articles/{closed['articleIds'][0]}"))
    assert "원정" in recap["tags"] and recap["requestJson"]["sessionSummary"]["ourResult"]["wins"] == 1
    assert "한강FC" in recap["content"]
    post = [i for i in api.ok(api.get("/admin/insights", params={"sessionId": sid})) if i["phase"] == "POST"]
    rec = next(i for i in post if i["type"] == "OPPONENT_RECORD")["facts"]
    assert (rec["todayMatches"], rec["todayWins"], rec["todayLosses"], rec["firstMeeting"]) == (2, 1, 1, True)

    # 같은 상대(직접추가에서 공백 · 대소문자를 다르게 써도 같은 팀)와 두 번째 원정: 지난 전적이 프리뷰 사실로
    sid2, _, _, _ = _away_session(api, ids, "2027-01-30", opponent="한강fc")
    pre = next(i for i in api.ok(api.get("/admin/insights", params={"sessionId": sid2})) if i["type"] == "OPPONENT_RECORD")
    assert pre["facts"]["firstMeeting"] is False and (pre["facts"]["wins"], pre["facts"]["losses"]) == (1, 1)


def test_away_sessions_do_not_block_internal_order(make_club):
    api = make_club("away4")
    ids = _members(api)
    # 마감된 원정 일정이 더 늦은 날짜여도 내부 일정 생성은 막지 않는다(실력 점수와 무관)
    sid, _, ours, opp = _away_session(api, ids, "2027-02-20")
    m = _match(api, sid, ours, opp, ids[:3])
    api.ok(api.post(f"/matches/{m}/start"))
    api.ok(api.post(f"/matches/{m}/end"))
    api.ok(api.post(f"/sessions/{sid}/close"))
    internal = api.ok(api.post("/sessions", {"sessionDate": "2027-02-10"}), 201)["sessionId"]

    # 앞 날짜의 열린 원정 일정은 내부 일정 마감 순서에 끼지 않는다
    open_away, _, _, _ = _away_session(api, ids, "2027-02-05")
    api.ok(api.post(f"/sessions/{internal}/members", {"memberIds": ids}))
    gen = api.ok(api.post(f"/sessions/{internal}/teams/generate", {"teamCount": 2, "seed": 1}))
    conf = api.ok(api.post(f"/sessions/{internal}/teams/confirm", {"generationId": gen["generationId"]}))
    assert conf["away"] is False and all(not t["opponent"] for t in conf["teams"])
    mm = api.next_match(internal)
    api.ok(api.post(f"/matches/{mm['matchId']}/start"))
    api.ok(api.post(f"/matches/{mm['matchId']}/end"))
    assert api.ok(api.post(f"/sessions/{internal}/close"))["status"] == "CLOSED"
    # 반대로 원정 일정 마감도 앞선 열린 일정과 무관
    assert api.ok(api.post(f"/sessions/{open_away}/close"))["status"] == "CLOSED"


def _play(api, sid, ours, opp, lineup, goals_for, goals_against, scorer, assist=None):
    """원정 경기 하나: 우리 골(scorer, 첫 골만 assist) goals_for개 + 원정팀 골 goals_against개 → 종료 · 확정."""
    mid = _match(api, sid, ours, opp, lineup)
    api.ok(api.post(f"/matches/{mid}/start"))
    for i in range(goals_for):
        api.ok(_goal(api, mid, ours, scorer, assist if i == 0 else None))
    for _ in range(goals_against):
        api.ok(_goal(api, mid, opp))
    api.ok(api.post(f"/matches/{mid}/end"))
    api.ok(api.post(f"/matches/{mid}/finalize"))
    return mid


def test_opponent_management_rename_hide_restore(make_club):
    api = make_club("away5")
    ids = _members(api)
    sid, _, ours, opp = _away_session(api, ids, "2027-03-06", opponent="한강FC")
    mid = _play(api, sid, ours, opp, ids[:4], 2, 1, ids[0], ids[1])
    api.ok(api.post(f"/sessions/{sid}/close"))
    hangang = api.ok(api.get(f"/sessions/{sid}", admin=False))["opponentId"]
    mapo = _opponent(api, "마포FC")

    # 관리자만, 숨긴 팀 포함 목록도 관리자만(일정 수 같이)
    assert api.patch(f"/opponents/{hangang}", {"name": "한강유나이티드"}, admin=False).status_code == 401
    assert api.get("/opponents", params={"includeHidden": "true"}, admin=False).status_code == 401
    full = api.ok(api.get("/opponents", params={"includeHidden": "true"}))
    assert {o["name"]: o["sessions"] for o in full} == {"한강FC": 1, "마포FC": 0}

    # 이름 수정: 지난 원정 일정 · 경기 화면 · 원정 기록 표시도 새 이름으로
    r = api.ok(api.patch(f"/opponents/{hangang}", {"name": "  한강   유나이티드 "}))
    assert r == {"opponentId": hangang, "name": "한강 유나이티드", "active": True, "sessions": 1}
    s = api.ok(api.get(f"/sessions/{sid}", admin=False))
    assert s["opponentName"] == "한강 유나이티드"
    assert next(t for t in s["teams"] if t["opponent"])["displayName"] == "한강 유나이티드"
    assert api.ok(api.get(f"/matches/{mid}", admin=False))["teamB"]["displayName"] == "한강 유나이티드"
    away = api.ok(api.get("/stats/away", admin=False))
    assert [o["opponentName"] for o in away["opponents"]] == ["한강 유나이티드"]
    assert away["recent"][0]["opponentName"] == "한강 유나이티드"
    # 같은 이름(공백 · 대소문자 무시)으로는 못 바꾼다, 빈 이름도 안 됨
    r = api.patch(f"/opponents/{mapo}", {"name": "한강유나이티드"})
    assert r.status_code == 409 and r.json()["error"]["code"] == "OPPONENT_EXISTS"
    assert api.patch(f"/opponents/{mapo}", {"name": "   "}).status_code == 400
    assert api.patch(f"/opponents/999999", {"active": False}).status_code == 404

    # 숨기기: 고르는 목록에서만 빠지고, 지난 전적 · 상대별 상세는 그대로. 숨긴 팀으로는 새 원정 편성 불가
    r = api.ok(api.patch(f"/opponents/{hangang}", {"active": False}))
    assert r["active"] is False
    assert [o["name"] for o in api.ok(api.get("/opponents", admin=False))] == ["마포FC"]
    assert [(o["name"], o["active"]) for o in api.ok(api.get("/opponents", params={"includeHidden": "true"}))] == \
        [("마포FC", True), ("한강 유나이티드", False)]
    assert api.ok(api.get("/stats/away", admin=False))["summary"]["matches"] == 1
    assert api.ok(api.get(f"/stats/away/opponents/{hangang}", admin=False))["opponent"]["active"] is False
    s2 = api.ok(api.post("/sessions", {"sessionDate": "2027-03-13"}), 201)["sessionId"]
    api.ok(api.post(f"/sessions/{s2}/members", {"memberIds": ids}))
    r = api.post(f"/sessions/{s2}/teams/generate", {"teamCount": 1, "opponentId": hangang})
    assert r.status_code == 404 and r.json()["error"]["code"] == "OPPONENT_NOT_FOUND"
    # 숨긴 팀과 같은 이름을 [직접추가]하면 그 팀이 다시 보인다(전적이 둘로 갈리지 않게)
    again = api.post("/opponents", {"name": "한강 유나이티드"})
    assert again.status_code == 200 and again.json() == {"opponentId": hangang, "name": "한강 유나이티드", "active": True}
    # 복원
    api.ok(api.patch(f"/opponents/{mapo}", {"active": False}))
    assert api.ok(api.patch(f"/opponents/{mapo}", {"active": True}))["active"] is True
    assert sorted(o["name"] for o in api.ok(api.get("/opponents", admin=False))) == ["마포FC", "한강 유나이티드"]


def test_away_opponent_detail(make_club):
    api = make_club("away6")
    ids = _members(api)
    # 한강FC와 두 번(1차: 2-1 승 · 0-1 패, 2차: 3-3 무), 마포FC와 한 번(1-0 승)
    s1, _, ours, opp = _away_session(api, ids, "2027-04-03", opponent="한강FC")
    _play(api, s1, ours, opp, ids[:4], 2, 1, ids[0], ids[1])
    _play(api, s1, ours, opp, ids[1:5], 0, 1, ids[1])
    api.ok(api.post(f"/sessions/{s1}/close"))
    s2, _, ours2, opp2 = _away_session(api, ids, "2027-04-10", opponent="마포FC")
    _play(api, s2, ours2, opp2, ids[:3], 1, 0, ids[2])
    api.ok(api.post(f"/sessions/{s2}/close"))
    s3, _, ours3, opp3 = _away_session(api, ids, "2027-04-17", opponent="한강fc")
    _play(api, s3, ours3, opp3, [ids[0], ids[3], ids[5]], 3, 3, ids[3], ids[0])
    api.ok(api.post(f"/sessions/{s3}/close"))

    hangang = api.ok(api.get(f"/sessions/{s1}", admin=False))["opponentId"]
    d = api.ok(api.get(f"/stats/away/opponents/{hangang}", admin=False))
    assert d["opponent"] == {"opponentId": hangang, "name": "한강FC", "active": True}
    assert d["summary"] == {"sessions": 2, "matches": 3, "wins": 1, "draws": 1, "losses": 1,
                            "goalsFor": 5, "goalsAgainst": 5}
    # 일정은 최근 순, 경기는 경기 순서대로
    assert [x["sessionId"] for x in d["sessions"]] == [s3, s1]
    assert [(m["gameNo"], m["scoreFor"], m["scoreAgainst"], m["result"]) for m in d["sessions"][1]["matches"]] == \
        [(1, 2, 1, "W"), (2, 0, 1, "L")]
    assert (d["sessions"][1]["wins"], d["sessions"][1]["losses"], d["sessions"][0]["draws"]) == (1, 1, 1)
    # 그 팀 상대 우리 선수 기록(골 → 도움 순), 마포FC 경기는 빠진다
    rows = {x["memberId"]: x for x in d["members"]}
    assert d["members"][0]["memberId"] == ids[3] and rows[ids[3]]["goals"] == 3
    assert (rows[ids[0]]["goals"], rows[ids[0]]["assists"], rows[ids[0]]["games"]) == (2, 1, 2)
    assert (rows[ids[1]]["assists"], rows[ids[1]]["games"], rows[ids[1]]["losses"]) == (1, 2, 1)
    assert ids[2] in rows and rows[ids[2]]["goals"] == 0  # 마포FC전 골은 세지 않는다
    # 상대 전체 목록의 opponentId로 들어온다, 다른 클럽 · 없는 팀은 404
    away = api.ok(api.get("/stats/away", admin=False))
    assert {o["opponentName"]: o["opponentId"] for o in away["opponents"]}["한강FC"] == hangang
    assert api.get("/stats/away/opponents/999999", admin=False).status_code == 404
    other = make_club("away6b")
    assert other.get(f"/stats/away/opponents/{hangang}", admin=False).status_code == 404
