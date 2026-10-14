from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import BadRequest
from app.models import Member
from app.services.common import get_member
from app.services.config_service import load_config
from app.services.rating_service import ensure_player_rating


def list_members(db: Session, club_id: int, include_inactive: bool = False) -> list[Member]:
    stmt = select(Member).where(Member.club_id == club_id)
    if not include_inactive:
        stmt = stmt.where(Member.active_yn.is_(True))
    return list(db.scalars(stmt.order_by(Member.display_order, Member.name)))


def create_member(db: Session, club_id: int, name: str, joined_at: date | None = None,
                  profile_image_url: str | None = None, display_order: int | None = None,
                  initial_rating: float | None = None) -> Member:
    name = (name or "").strip()
    if not name:
        raise BadRequest("이름은 필수입니다.")
    m = Member(club_id=club_id, name=name, joined_at=joined_at, profile_image_url=profile_image_url,
               display_order=display_order, active_yn=True, initial_rating=initial_rating)
    db.add(m)
    db.flush()
    # 신규: 시작 Rating(지정값 또는 설정 INITIAL_RATING), Confidence 0
    ensure_player_rating(db, m, load_config(db, club_id))
    db.commit()
    return m


def update_member(db: Session, club_id: int, member_id: int, **fields) -> Member:
    m = get_member(db, club_id, member_id)
    for k in ("name", "joined_at", "profile_image_url", "display_order", "active_yn"):
        if k in fields and fields[k] is not None:
            v = fields[k]
            if k == "name":
                v = v.strip()
                if not v:
                    raise BadRequest("이름은 필수입니다.")
            setattr(m, k, v)
    db.commit()
    return m
