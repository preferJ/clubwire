"""클럽 주소 변경은 ID, 관리자 인증 및 기존 기록을 보존한다."""
import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.core.errors import BadRequest, Conflict, NotFound
from app.models import AiArticle, Club, ClubAdmin, ClubSession, Member, SystemConfig
from app.services import club_service
from tests.conftest import Api
from tests.test_article_writer import _preview


def _records(db, club_id):
    return {
        "admins": list(db.execute(select(ClubAdmin.admin_id, ClubAdmin.password_hash)
                                  .where(ClubAdmin.club_id == club_id).order_by(ClubAdmin.admin_id))),
        "members": list(db.execute(select(Member.member_id, Member.name, Member.initial_rating)
                                   .where(Member.club_id == club_id).order_by(Member.member_id))),
        "sessions": list(db.execute(select(ClubSession.session_id, ClubSession.status)
                                    .where(ClubSession.club_id == club_id).order_by(ClubSession.session_id))),
        "articles": list(db.execute(select(AiArticle.article_id, AiArticle.session_id, AiArticle.content,
                                            AiArticle.published_yn)
                                    .where(AiArticle.club_id == club_id).order_by(AiArticle.article_id))),
        "config": list(db.execute(select(SystemConfig.config_key, SystemConfig.config_value)
                                  .where(SystemConfig.club_id == club_id).order_by(SystemConfig.config_key))),
    }


def test_rename_preserves_records_and_existing_admin_token(make_club, db):
    old = make_club("slug-records-old")
    article = _preview(old)
    old.ok(old.post(f"/articles/{article['articleId']}/publish"))
    old.ok(old.patch("/admin/config", {"values": {"AI_TEMPERATURE": 0.3}}))
    info = old.ok(old.get("", admin=False))
    club_id = info["clubId"]
    club = db.get(Club, club_id)
    config_version = club.config_version
    before = _records(db, club_id)
    assert len(before["members"]) == 6 and len(before["sessions"]) == len(before["articles"]) == 1

    renamed = club_service.rename_club(db, old.slug, "slug-records-new", " YPR ")
    assert renamed.club_id == club_id and renamed.club_name == "YPR"
    assert renamed.config_version == config_version
    assert _records(db, club_id) == before

    new = Api(old.c, "slug-records-new")
    new.token = old.token
    assert new.ok(new.get("", admin=False))["clubName"] == "YPR"
    assert new.ok(new.get("/admin/me"))["clubId"] == club_id
    assert len(new.ok(new.get("/members", admin=False))) == 6
    assert new.ok(new.get(f"/sessions/{article['sessionId']}", admin=False))["sessionId"] == article["sessionId"]
    assert new.ok(new.get(f"/articles/{article['articleId']}", admin=False))["content"] == article["content"]
    assert old.get("", admin=False).status_code == 404
    assert old.get("/admin/me").status_code == 404
    new.login()  # 이전 PIN도 계속 사용할 수 있다.


def test_rename_refuses_existing_target_without_merging(make_club, db):
    source = make_club("slug-conflict-source")
    target = make_club("slug-conflict-target")
    source_info = source.ok(source.get("", admin=False))
    target_info = target.ok(target.get("", admin=False))
    source_records = _records(db, source_info["clubId"])
    target_records = _records(db, target_info["clubId"])

    with pytest.raises(Conflict, match="이미 사용 중"):
        club_service.rename_club(db, source.slug, target.slug, "YPR")

    assert source.ok(source.get("", admin=False)) == source_info
    assert target.ok(target.get("", admin=False)) == target_info
    assert _records(db, source_info["clubId"]) == source_records
    assert _records(db, target_info["clubId"]) == target_records


@pytest.mark.parametrize("case,new_slug,new_name", [
    ("empty", "", "YPR"), ("uppercase", "YPR", "YPR"), ("space", "with space", "YPR"),
    ("slash", "c/ypr", "YPR"), ("unicode", "가나다", "YPR"), ("long", "x" * 51, "YPR"),
    ("blank-name", "slug-valid", "  "), ("long-name", "slug-valid", "가" * 101),
])
def test_invalid_rename_has_no_partial_change(make_club, db, case, new_slug, new_name):
    api = make_club(f"slug-invalid-{case}")
    before = api.ok(api.get("", admin=False))
    with pytest.raises(BadRequest):
        club_service.rename_club(db, api.slug, new_slug, new_name)
    assert api.ok(api.get("", admin=False)) == before


def test_same_slug_can_rename_display_name_and_missing_source_is_not_found(make_club, db):
    api = make_club("slug-same")
    original = api.ok(api.get("", admin=False))
    assert club_service.rename_club(db, api.slug, api.slug).club_name == original["clubName"]
    assert club_service.rename_club(db, api.slug, api.slug, "YPR").club_id == original["clubId"]
    assert api.ok(api.get("", admin=False))["clubName"] == "YPR"
    with pytest.raises(NotFound):
        club_service.rename_club(db, "slug-missing-source", "slug-missing-target", "YPR")


def test_unique_conflict_rolls_back_name_and_slug(make_club, db, monkeypatch):
    api = make_club("slug-race-source")
    original = api.ok(api.get("", admin=False))

    def unique_conflict():
        db.flush()
        raise IntegrityError("UPDATE CLUB", {}, Exception("duplicate CLUB_SLUG"))

    monkeypatch.setattr(db, "commit", unique_conflict)
    with pytest.raises(Conflict):
        club_service.rename_club(db, api.slug, "slug-race-target", "YPR")
    assert db.get(Club, original["clubId"]).club_slug == api.slug
    assert api.ok(api.get("", admin=False)) == original
