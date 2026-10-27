"""로컬 테스트 초기화: 대상 격리, 원본 레이팅, 안내 기사, 백업 복구."""
from pathlib import Path
from datetime import date, datetime

import pytest
from sqlalchemy import func, select

from app.core.database import engine
from app.models import AiArticle, Club, ClubAdmin, ClubSession, Member, MemberStatSummary, PlayerRating
from app.services.club_service import club_summary
from scripts import reset_ypr_test as bootstrap
from tests.test_article_writer import _preview


def _count(db, model, club_id):
    return db.scalar(select(func.count()).select_from(model).where(model.club_id == club_id))


def test_reset_is_scoped_and_restorable(make_club, db, tmp_path):
    api = make_club("resetlocal")
    old_article = _preview(api)
    regenerated = api.ok(api.post(f"/articles/{old_article['articleId']}/regenerate"), 201)
    other = make_club("resetother")
    other_article = _preview(other)
    club = db.scalar(select(Club).where(Club.club_slug == api.slug))
    other_club = db.scalar(select(Club).where(Club.club_slug == other.slug))
    original_ids = list(db.scalars(select(Member.member_id).where(Member.club_id == club.club_id).order_by(Member.member_id)))
    admin_hash = db.scalar(select(ClubAdmin.password_hash).where(ClubAdmin.club_id == club.club_id))
    api.ok(api.patch("/admin/config", {"values": {"MATCH_DURATION_SEC": 720}}))
    before = bootstrap.preview_reset(db, club)
    assert _count(db, Member, club.club_id) == 6
    assert bootstrap.preview_reset(db, club) == before
    result = bootstrap.reset_club(db, club, tmp_path)
    backup = Path(result["backup_path"])
    assert backup.is_file() and backup.stat().st_size > 0
    assert admin_hash not in backup.read_text(encoding="utf-8")
    assert "FOREIGN_KEY_CHECKS" not in backup.read_text(encoding="utf-8").upper()
    rows = db.execute(select(Member.name, Member.initial_rating, PlayerRating.current_rating,
                             PlayerRating.match_sample_count, PlayerRating.last_played_date)
                      .join(PlayerRating, Member.member_id == PlayerRating.member_id)
                      .where(Member.club_id == club.club_id).order_by(Member.display_order)).all()
    assert [(r.name, r.initial_rating) for r in rows] == list(bootstrap.ROSTER)
    assert len(rows) == 23
    assert all(r.current_rating == r.initial_rating and r.match_sample_count == 0 and r.last_played_date is None for r in rows)
    assert _count(db, MemberStatSummary, club.club_id) == 23
    assert _count(db, ClubSession, club.club_id) == 0
    assert _count(db, AiArticle, club.club_id) == 1
    notice = api.ok(api.get(f"/articles/{result['article_id']}", admin=False))
    assert notice["articleType"] == "NOTICE" and notice["status"] == "PUBLISHED"
    assert notice["title"] == "YPR clubWire 테스트 기간 돌입"
    assert notice["sessionId"] is None and "공지" in notice["tags"]
    assert notice["content"] == bootstrap.NOTICE_BODY
    assert api.ok(api.get("/articles", params={"tag": "공지"}, admin=False))[0]["articleId"] == result["article_id"]
    assert api.ok(api.get("/summary", admin=False))["articles"] == 1
    assert api.post(f"/articles/{result['article_id']}/regenerate").status_code == 400
    assert db.scalar(select(ClubAdmin.password_hash).where(ClubAdmin.club_id == club.club_id)) == admin_hash
    assert api.ok(api.get("/admin/config"))["items"]
    assert next(i for i in api.ok(api.get("/admin/config"))["items"] if i["key"] == "MATCH_DURATION_SEC")["value"] == 720
    assert _count(db, Member, other_club.club_id) == 6
    assert other.ok(other.get(f"/articles/{other_article['articleId']}"))["articleId"] == other_article["articleId"]

    # 백업 SQL을 직접 실행해 자기 참조 재생성 기사까지 원래대로 복구한다.
    db.commit()
    raw = engine.raw_connection()
    try:
        with raw.cursor() as cursor:
            statements = "\n".join(line for line in backup.read_text(encoding="utf-8").splitlines() if not line.lstrip().startswith("--"))
            for statement in statements.split(";"):
                if statement.strip():
                    cursor.execute(statement)
        raw.commit()
    finally:
        raw.close()
    db.expire_all()
    assert list(db.scalars(select(Member.member_id).where(Member.club_id == club.club_id).order_by(Member.member_id))) == original_ids
    assert _count(db, AiArticle, club.club_id) == 2
    assert db.get(AiArticle, regenerated["articleId"]).parent_article_id == old_article["articleId"]
    assert _count(db, Member, other_club.club_id) == 6


def test_backup_failure_does_not_delete_data(make_club, db, tmp_path):
    api = make_club("resetbackupfail")
    _preview(api)
    club = db.scalar(select(Club).where(Club.club_slug == api.slug))
    before = bootstrap.preview_reset(db, club)
    bad_dir = tmp_path / "not-a-directory"
    bad_dir.write_text("keep this file", encoding="utf-8")
    with pytest.raises(OSError):
        bootstrap.reset_club(db, club, bad_dir)
    assert bootstrap.preview_reset(db, club) == before
    assert bad_dir.read_text(encoding="utf-8") == "keep this file"


def test_reset_failure_rolls_back_deleted_data(make_club, db, tmp_path, monkeypatch):
    api = make_club("resetrollback")
    _preview(api)
    club = db.scalar(select(Club).where(Club.club_slug == api.slug))
    before = bootstrap.preview_reset(db, club)
    def fail_rating(*_args, **_kwargs):
        raise RuntimeError("seed failed")
    monkeypatch.setattr(bootstrap, "ensure_player_rating", fail_rating)
    with pytest.raises(RuntimeError, match="seed failed"):
        bootstrap.reset_club(db, club, tmp_path)
    assert bootstrap.preview_reset(db, club) == before
    assert len(list(tmp_path.glob("*.sql"))) == 1


def test_standalone_notice_count_uses_club_local_year(make_club, db):
    api = make_club("noticeyear")
    club = db.scalar(select(Club).where(Club.club_slug == api.slug))
    for published in (datetime(2025, 12, 31, 15), datetime(2026, 12, 31, 15)):
        db.add(AiArticle(club_id=club.club_id, article_type="NOTICE", title="안내", content="본문", model_name="manual",
                         prompt_version="manual_notice_v1", status="PUBLISHED", published_yn=True, published_at=published))
    db.commit()
    assert club_summary(db, club, date(2026, 1, 1))["articles"] == 1
