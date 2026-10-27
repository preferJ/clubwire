"""클럽별 공개 운영수칙과 상단 공지. 변경 알림은 커밋 이후에만 전송한다."""
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.database import emit
from app.core.errors import NotFound
from app.core.timeutil import to_iso, utcnow
from app.models import Club


def serialize_content(club: Club) -> dict:
    return {
        "operatingRules": club.operating_rules,
        "operatingRulesUpdatedAt": to_iso(club.operating_rules_updated_at),
        "announcement": club.announcement or "",
        "announcementUpdatedAt": to_iso(club.announcement_updated_at),
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

    if changed:
        emit(db, club_id, "CLUB_CONTENT_UPDATED", {})
    db.commit()
    return club
