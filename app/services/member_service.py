from datetime import date, timedelta

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
                  initial_rating: float | None = None, birth_year: int | None = None,
                  jersey_number: int | None = None) -> Member:
    name = (name or "").strip()
    if not name:
        raise BadRequest("이름은 필수입니다.")
    _check_profile(joined_at, birth_year)
    _check_jersey_number(jersey_number)
    m = Member(club_id=club_id, name=name, joined_at=joined_at, profile_image_url=profile_image_url,
               display_order=display_order, active_yn=True, initial_rating=initial_rating, birth_year=birth_year,
               jersey_number=jersey_number)
    db.add(m)
    db.flush()
    # 신규: 시작 Rating(지정값 또는 설정 INITIAL_RATING), Confidence 0
    ensure_player_rating(db, m, load_config(db, club_id))
    db.commit()
    return m


# None을 넘기면 값을 지우는 항목(나머지는 None = 변경 없음)
CLEARABLE = ("joined_at", "birth_year", "jersey_number")


def update_member(db: Session, club_id: int, member_id: int, **fields) -> Member:
    m = get_member(db, club_id, member_id)
    _check_profile(fields.get("joined_at"), fields.get("birth_year"))
    _check_jersey_number(fields.get("jersey_number"))
    for k in ("name", "joined_at", "birth_year", "jersey_number", "profile_image_url", "display_order", "active_yn"):
        if k in fields and (fields[k] is not None or k in CLEARABLE):
            v = fields[k]
            if k == "name":
                v = v.strip()
                if not v:
                    raise BadRequest("이름은 필수입니다.")
            setattr(m, k, v)
    db.commit()
    return m


def _check_profile(joined_at: date | None, birth_year: int | None) -> None:
    """가입일 · 출생연도 범위 확인(미래 날짜 · 미래 연도 불가). 서버(UTC)와 클럽 현지 날짜 차이로 하루 여유를 둔다."""
    today = date.today()
    if joined_at is not None and joined_at > today + timedelta(days=1):
        raise BadRequest("가입일은 오늘 이후로 정할 수 없어요.")
    if birth_year is not None and not (1900 <= birth_year <= today.year):
        raise BadRequest(f"출생연도는 1900~{today.year} 사이로 입력하세요.")


def _check_jersey_number(number: int | None) -> None:
    if number is not None and (type(number) is not int or not 0 <= number <= 99):
        raise BadRequest("등번호는 0~99 사이의 정수로 입력하세요.")
