"""클럽별 공개 운영수칙과 상단 공지(+ 공지 크기 · 스타일). 변경 알림은 커밋 이후에만 전송한다."""
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.database import emit
from app.core.errors import NotFound
from app.core.timeutil import to_iso, utcnow
from app.models import Club

ANNOUNCEMENT_SIZES = ("small", "medium", "large")
ANNOUNCEMENT_SIZE_DEFAULT = "medium"
# 상단 공지 스타일: 기본 / 강조(연한 클럽 색 바탕 + 굵은 글씨) / 클럽 색(진한 바탕 + 흰 글씨) / 긴급(노란 바탕 + 깜박이는 표시 + 빠른 흐름)
ANNOUNCEMENT_STYLES = ("default", "highlight", "accent", "alert")
ANNOUNCEMENT_STYLE_DEFAULT = "default"


def serialize_content(club: Club) -> dict:
    return {
        "operatingRules": club.operating_rules,
        "operatingRulesUpdatedAt": to_iso(club.operating_rules_updated_at),
        "announcement": club.announcement or "",
        "announcementUpdatedAt": to_iso(club.announcement_updated_at),
        "announcementSize": club.announcement_size if club.announcement_size in ANNOUNCEMENT_SIZES
        else ANNOUNCEMENT_SIZE_DEFAULT,
        "announcementStyle": club.announcement_style if club.announcement_style in ANNOUNCEMENT_STYLES
        else ANNOUNCEMENT_STYLE_DEFAULT,
    }


def update_content(db: Session, club_id: int, changes: dict) -> Club:
    club = db.scalar(select(Club).where(Club.club_id == club_id, Club.active_yn.is_(True)).with_for_update())
    if club is None:
        raise NotFound("클럽을 찾을 수 없습니다.", "CLUB_NOT_FOUND")

    changed = False
    now = utcnow()
    # MySQL DATETIME(3)의 반올림으로 PATCH 응답과 재조회 시각이 달라지지 않게 맞춘다.
    changed_at = now.replace(microsecond=(now.microsecond // 1000) * 1000)
    for field in ("operating_rules", "announcement"):
        if field not in changes:
            continue
        value = changes[field]
        if field == "announcement":
            # 공지는 여러 줄을 붙여 넣어도 공개 화면에서 한 줄로 흐른다.
            value = " ".join((value or "").split()) or None
        elif value is not None:
            value = value.strip()
        if getattr(club, field) != value:
            setattr(club, field, value)
            setattr(club, field + "_updated_at", changed_at)
            changed = True
    if "announcement_size" in changes:
        # 기본값(medium)은 NULL로 둔다. 크기만 바꾸면 공지 문구 수정 시각은 그대로
        size = changes["announcement_size"] or ANNOUNCEMENT_SIZE_DEFAULT
        stored = None if size == ANNOUNCEMENT_SIZE_DEFAULT else size
        if club.announcement_size != stored:
            club.announcement_size = stored
            changed = True
    if "announcement_style" in changes:
        # 기본값(default)은 NULL로 둔다. 스타일만 바꾸면 공지 문구 수정 시각은 그대로
        style = changes["announcement_style"] or ANNOUNCEMENT_STYLE_DEFAULT
        stored = None if style == ANNOUNCEMENT_STYLE_DEFAULT else style
        if club.announcement_style != stored:
            club.announcement_style = stored
            changed = True

    if changed:
        emit(db, club_id, "CLUB_CONTENT_UPDATED", {})
    db.commit()
    return club
