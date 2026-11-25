"""관리자 선정은 순위와 독립적이며, 월별 수상/기사 교체와 권한을 보장한다."""
from datetime import timedelta

from sqlalchemy import func, select

from app.core.database import SessionLocal
from app.core.timeutil import local_today, month_range, prev_month_start
from app.models import AiArticle, ClubAdmin, ClubSession, MemberTitle, TitleType
from app.services import mvp_service
from app.services.common import get_club_by_slug
from app.wire import article_service


def _member(api, name):
    return api.ok(api.post("/members", {"name": name}), 201)["memberId"]


def _month():
    return local_today("Asia/Seoul").strftime("%Y-%m")


def _awards(api):
    return [a for a in api.ok(api.get("/titles/awards")) if a["titleCode"] == "MONTHLY_MVP"]


def test_no_session_selection_publishes_once_and_keeps_zero_facts(make_club):
    api = make_club("manualempty")
    mid = _member(api, "새 선수")
    month = _month()
    assert api.ok(api.get("/monthly-mvp", params={"month": month}))["winners"] == []
    result = api.ok(api.post(f"/members/{mid}/monthly-mvp", {"month": month}))
    assert result["changed"] and result["winners"] == [{"memberId": mid, "name": "새 선수"}]
    status = api.ok(api.get("/monthly-mvp", params={"month": month}))
    assert status["articleId"] == result["articleId"] and status["articleStatus"] == "PUBLISHED"
    article = api.ok(api.get(f"/articles/{result['articleId']}"))
    assert article["sessionId"] is None and article["usedInsightIds"] == []
    assert "관리자가" in article["summary"] and "확정된 내부 경기 기록은 없다" in article["content"]
    facts = article["requestJson"]["monthlyMvp"]
    winner = facts["winners"][0]
    assert facts["selection"] == "manual" and facts["runnersUp"] == [] and facts["tiebreak"] is None
    assert all(winner[k] == 0 for k in ("points", "winPoints", "wins", "draws", "losses", "sessions", "games", "goals", "assists"))
    assert winner["ratio"] == 1
    again = api.ok(api.post(f"/members/{mid}/monthly-mvp", {"month": month}))
    assert not again["changed"] and again["articleId"] == result["articleId"]
    assert len(_awards(api)) == 1
    with SessionLocal() as db:
        club = get_club_by_slug(db, api.slug)
        assert db.scalar(select(func.count()).select_from(ClubSession).where(ClubSession.club_id == club.club_id)) == 0
        assert db.scalar(select(func.count()).select_from(AiArticle).where(AiArticle.club_id == club.club_id)) == 1
    assert api.ok(api.get("/stats/mvp-race", admin=False))["candidates"] == []


def test_replacement_preserves_history_and_blocks_old_article(make_club):
    api = make_club("manualreplace")
    first, second = _member(api, "첫 선정"), _member(api, "새 선정")
    month = _month()
    old = api.ok(api.post(f"/members/{first}/monthly-mvp", {"month": month}))
    conflict = api.post(f"/members/{second}/monthly-mvp", {"month": month})
    assert conflict.status_code == 409 and "MVP_REPLACE_REQUIRED" in conflict.text
    assert _awards(api)[0]["memberId"] == first
    new = api.ok(api.post(f"/members/{second}/monthly-mvp", {"month": month, "replace": True}))
    assert new["articleId"] != old["articleId"]
    assert [a["memberId"] for a in _awards(api)] == [second]
    assert api.get(f"/articles/{old['articleId']}", admin=False).status_code == 404
    assert api.ok(api.get(f"/articles/{old['articleId']}"))["status"] == "SUPERSEDED"
    for operation in ("publish", "regenerate"):
        response = api.post(f"/articles/{old['articleId']}/{operation}")
        assert response.status_code == 409 and "MVP_SELECTION_CHANGED" in response.text
    with SessionLocal() as db:
        club = get_club_by_slug(db, api.slug)
        rows = list(db.scalars(select(MemberTitle).join(TitleType).where(
            MemberTitle.club_id == club.club_id, TitleType.title_code == "MONTHLY_MVP")
            .order_by(MemberTitle.member_title_id)))
        assert [(r.member_id, r.cancelled_yn) for r in rows] == [(first, True), (second, False)]
    api.ok(api.post(f"/titles/awards/{_awards(api)[0]['memberTitleId']}/cancel"))
    assert api.get(f"/articles/{new['articleId']}", admin=False).status_code == 404
    assert api.ok(api.get("/monthly-mvp", params={"month": month}))["winners"] == []
    with SessionLocal() as db:
        club = get_club_by_slug(db, api.slug)
        assert mvp_service.close_due_month(db, club) == []
    assert _awards(api) == []


def test_months_are_independent_and_last_month_links_latest_generation(make_club):
    api = make_club("manualmonths")
    mid = _member(api, "월별 선수")
    previous = prev_month_start(local_today("Asia/Seoul")).strftime("%Y-%m")
    old = api.ok(api.post(f"/members/{mid}/monthly-mvp", {"month": previous}))
    current = api.ok(api.post(f"/members/{mid}/monthly-mvp", {"month": _month()}))
    assert api.get(f"/articles/{old['articleId']}", admin=False).status_code == 200
    assert api.get(f"/articles/{current['articleId']}", admin=False).status_code == 200
    regenerated = api.ok(api.post(f"/articles/{old['articleId']}/regenerate"), 201)
    assert regenerated["status"] == "PUBLISHED"
    race = api.ok(api.get("/stats/mvp-race", admin=False))
    assert race["lastMonth"]["month"] == previous and race["lastMonth"]["articleId"] == regenerated["articleId"]
    assert api.get(f"/articles/{current['articleId']}", admin=False).status_code == 200
    status = api.ok(api.get("/monthly-mvp", params={"month": previous}))
    assert status["articleId"] == regenerated["articleId"]


def test_selection_requires_club_admin_live_member_and_valid_month(make_club):
    api, other = make_club("manualauth"), make_club("manualother")
    mid, outsider = _member(api, "선수"), _member(other, "다른 팀 선수")
    month = _month()
    assert api.get("/monthly-mvp", params={"month": month}, admin=False).status_code == 401
    assert api.post(f"/members/{mid}/monthly-mvp", {"month": month}, admin=False).status_code == 401
    assert api.post(f"/members/{outsider}/monthly-mvp", {"month": month}).status_code == 404
    future = (month_range(local_today("Asia/Seoul"))[1] + timedelta(days=1)).strftime("%Y-%m")
    assert api.post(f"/members/{mid}/monthly-mvp", {"month": future}).status_code == 400
    assert api.post(f"/members/{mid}/monthly-mvp", {"month": "2026-13"}).status_code == 400
    assert api.post(f"/members/{mid}/monthly-mvp", {"month": "invalid"}).status_code == 422
    bypass = api.post("/titles/awards", {"titleCode": "MONTHLY_MVP", "memberId": mid, "awardDate": month + "-01"})
    assert bypass.status_code == 400 and "USE_MONTHLY_MVP_SELECTION" in bypass.text
    api.ok(api.delete(f"/members/{mid}"))
    assert api.post(f"/members/{mid}/monthly-mvp", {"month": month}).status_code == 404


def test_changed_selection_during_generation_never_publishes_stale_winner(make_club, monkeypatch):
    api = make_club("manualgeneration")
    first, second = _member(api, "생성 중 선수"), _member(api, "변경 선수")
    month = _month()
    with SessionLocal() as db:
        club = get_club_by_slug(db, api.slug)
        admin_id = db.scalar(select(ClubAdmin.admin_id).where(ClubAdmin.club_id == club.club_id))
        old = mvp_service.select_monthly_mvp(db, club, first, month, admin_id)
    replacement = {}

    class ReplacingWriter:
        provider = "stub"

        def write(self, payload, model, options=None):
            # External AI is still writing when another request selects a different winner.
            with SessionLocal() as db:
                club = get_club_by_slug(db, api.slug)
                replacement.update(mvp_service.select_monthly_mvp(db, club, second, month, admin_id, replace=True))
            return article_service.template_writer().write(payload, model, options)

    monkeypatch.setattr(article_service, "get_writer", lambda: ReplacingWriter())
    article_service.run_generation(old["articleId"])
    assert replacement["changed"]
    assert api.ok(api.get(f"/articles/{old['articleId']}"))["status"] == "SUPERSEDED"
    assert api.get(f"/articles/{old['articleId']}", admin=False).status_code == 404
    monkeypatch.setattr(article_service, "get_writer", article_service.template_writer)
    article_service.run_generation(replacement["articleId"])
    assert api.ok(api.get(f"/articles/{replacement['articleId']}", admin=False))["status"] == "PUBLISHED"
    assert [a["memberId"] for a in _awards(api)] == [second]
