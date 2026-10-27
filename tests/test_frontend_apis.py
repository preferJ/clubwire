"""프론트 화면용 조회 API: LIVE 배너, 일정 목록 인원수, 일정 요약, 멤버별 수상 이력, 기사 목록 페이지."""
from datetime import datetime

from sqlalchemy import func, select, update

from app.models import AiArticle, MemberTitle


def test_live_summary_and_awards(make_club):
    api = make_club("front")
    ids = [api.ok(api.post("/members", {"name": f"F{i}"}), 201)["memberId"] for i in range(6)]
    sid = api.ok(api.post("/sessions", {"sessionDate": "2026-12-12"}), 201)["sessionId"]
    api.ok(api.post(f"/sessions/{sid}/members", {"memberIds": ids}))
    api.ok(api.post(f"/sessions/{sid}/guests", {"count": 1}))
    lst = api.ok(api.get("/sessions", admin=False))
    assert lst[0]["attendeeCount"] == 6 and lst[0]["guestCount"] == 1
    # 와이어 상단 요약 줄: 활동 멤버 · 올해(클럽 현지 날짜 기준) 일정 · 올해 게시 기사
    summary = api.ok(api.get("/summary", admin=False))
    assert summary["activeMembers"] == 6 and summary["articles"] == 0
    assert summary["sessions"] == (1 if summary["year"] == 2026 else 0)

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

    # 수동 타이틀(클럽이 직접 만든 것)은 여전히 수여·조회 가능
    api.ok(api.post("/titles/types", {"titleCode": "BEST_GK", "titleName": "이주의 수문장"}), 201)
    api.ok(api.post("/titles/awards", {"titleCode": "BEST_GK", "memberId": scorer, "sessionId": sid}), 201)
    mine = api.ok(api.get("/titles/awards", params={"memberId": scorer}, admin=False))
    assert mine[0]["titleCode"] == "BEST_GK" and mine[0]["memberName"] == "F" + str(ids.index(scorer))


def test_inactive_title_history_is_hidden(make_club, db):
    """비활성 타이틀(제거된 MVP 등)의 지난 수여 이력은 조회에서 빠진다(DB에는 남음)."""
    api = make_club("oldmvp")
    mid = api.ok(api.post("/members", {"name": "G0"}), 201)["memberId"]
    t = api.ok(api.post("/titles/types", {"titleCode": "MVP", "titleName": "이주의 MVP"}), 201)
    api.ok(api.post("/titles/awards", {"titleCode": "MVP", "memberId": mid, "awardDate": "2026-12-06"}), 201)
    assert [a["titleCode"] for a in api.ok(api.get("/titles/awards", admin=False))] == ["MVP"]
    api.ok(api.patch(f"/titles/types/{t['titleTypeId']}", {"active": False}))  # = alembic 0004
    assert api.ok(api.get("/titles/awards", admin=False)) == []
    assert db.scalar(select(func.count()).select_from(MemberTitle)
                     .where(MemberTitle.member_id == mid, MemberTitle.cancelled_yn.is_(False))) == 1


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


def test_member_profile_joined_and_birth_year(make_club):
    """선수 프로필: 관리자가 가입일 · 출생연도 입력 → 선수 기록(공개)에 표시. null은 지움, 안 보내면 그대로."""
    api = make_club("profile")
    mid = api.ok(api.post("/members", {"name": "홍길동"}), 201)["memberId"]
    m = api.ok(api.patch(f"/members/{mid}", {"joinedAt": "2021-03-14", "birthYear": 1992}))
    assert m["joinedAt"] == "2021-03-14" and m["birthYear"] == 1992
    assert api.ok(api.get(f"/stats/members/{mid}", admin=False))["profile"] == {
        "joinedAt": "2021-03-14", "birthYear": 1992, "jerseyNumber": None}

    # 이름만 바꾸면 가입일 · 출생연도는 그대로
    m = api.ok(api.patch(f"/members/{mid}", {"name": "홍길동A"}))
    assert m["joinedAt"] == "2021-03-14" and m["birthYear"] == 1992
    # null = 지움
    m = api.ok(api.patch(f"/members/{mid}", {"birthYear": None}))
    assert m["birthYear"] is None and m["joinedAt"] == "2021-03-14"

    # 범위 밖 · 미래 값 · 비관리자
    assert api.patch(f"/members/{mid}", {"birthYear": 1800}).status_code == 422
    assert api.patch(f"/members/{mid}", {"birthYear": 2099}).status_code == 400
    assert api.patch(f"/members/{mid}", {"joinedAt": "2099-01-01"}).status_code == 400
    assert api.patch(f"/members/{mid}", {"birthYear": 1990}, admin=False).status_code == 401


def test_summary_without_tzdata(make_club, monkeypatch):
    """Windows 기본 Python처럼 시간대 DB가 없어도 /summary가 동작(Asia/Seoul은 UTC+9 고정값으로 대체)."""
    from datetime import timedelta, timezone
    from zoneinfo import ZoneInfoNotFoundError

    from app.core import timeutil

    def no_tz(key):
        raise ZoneInfoNotFoundError(key)

    monkeypatch.setattr(timeutil, "ZoneInfo", no_tz)
    kst = timeutil.utcnow().replace(tzinfo=timezone.utc).astimezone(timezone(timedelta(hours=9))).date()
    assert timeutil.local_today("Asia/Seoul") == kst
    api = make_club("notz")
    assert api.ok(api.get("/summary", admin=False))["year"] == kst.year
