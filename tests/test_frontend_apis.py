"""프론트 화면용 조회 API: LIVE 배너, 일정 목록 인원수, 일정 요약, 멤버별 수상 이력, 기사 목록 페이지."""
from datetime import datetime

from sqlalchemy import update

from app.models import AiArticle


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


def test_article_pages_follow_publish_order(make_club, db):
    """기록 탭 지난 기사: 게시 순서(PUBLISHED_AT)와 ID 순서가 달라도 beforeId 페이지가 빠짐·중복 없이 이어진다."""
    api = make_club("feed")
    ids = [api.ok(api.post("/members", {"name": f"W{i}"}), 201)["memberId"] for i in range(4)]
    arts = []
    for day in ("2026-12-05", "2026-12-12", "2026-12-19"):
        sid = api.ok(api.post("/sessions", {"sessionDate": day}), 201)["sessionId"]
        api.ok(api.post(f"/sessions/{sid}/members", {"memberIds": ids}))
        gen = api.ok(api.post(f"/sessions/{sid}/teams/generate", {"teamCount": 2}))
        aid = api.ok(api.post(f"/sessions/{sid}/teams/confirm", {"generationId": gen["generationId"]}))["articleIds"][0]
        api.ok(api.post(f"/articles/{aid}/publish"))
        arts.append(aid)
    # 가장 오래된 기사(ID 최소)를 맨 나중에 게시한 상황(검토 대기로 두었다가 늦게 게시)
    db.execute(update(AiArticle).where(AiArticle.article_id == arts[0]).values(published_at=datetime(2027, 1, 1)))
    db.commit()

    seen, before = [], None
    for _ in range(5):
        page = api.ok(api.get("/articles", admin=False, params={"limit": 1, **({"beforeId": before} if before else {})}))
        if not page:
            break
        seen.append(page[0]["articleId"])
        before = page[0]["articleId"]
    assert seen == [arts[0], arts[2], arts[1]]

    # 와이어·기록 탭이 일정 날짜로 묶을 수 있도록 일정 날짜를 함께 준다
    by_id = {a["articleId"]: a for a in api.ok(api.get("/articles", admin=False))}
    assert by_id[arts[0]]["sessionDate"] == "2026-12-05" and by_id[arts[2]]["sessionDate"] == "2026-12-19"
