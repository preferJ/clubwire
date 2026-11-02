from datetime import date, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import BadRequest, Conflict
from app.core.timeutil import utcnow
from app.models import ClubSession, Member, SessionMember
from app.models.enums import AttendanceStatus, SessionStatus
from app.services.common import get_member
from app.services.config_service import load_config
from app.services.rating_service import ensure_player_rating


def list_members(db: Session, club_id: int, include_inactive: bool = False, deleted: bool = False) -> list[Member]:
    """deleted=False: 삭제 안 한 선수(기본은 활동 중만). deleted=True: 삭제한 선수만(최근 삭제 순, 관리자 보관함)."""
    stmt = select(Member).where(Member.club_id == club_id)
    if deleted:
        return list(db.scalars(stmt.where(Member.deleted_at.is_not(None))
                               .order_by(Member.deleted_at.desc(), Member.member_id.desc())))
    stmt = stmt.where(Member.deleted_at.is_(None))
    if not include_inactive:
        stmt = stmt.where(Member.active_yn.is_(True))
    return list(db.scalars(stmt.order_by(Member.display_order, Member.name)))


def delete_member(db: Session, club_id: int, member_id: int) -> Member:
    """선수 삭제 = DELETED_AT 기록(행 · 지난 경기 · 기사 · 수상 기록은 그대로). 이미 삭제했으면 그대로 둔다.
    예정 · 진행 중 일정에 참석으로 잡혀 있으면 팀 편성 · 경기와 어긋나므로 먼저 참석을 빼야 한다."""
    m = get_member(db, club_id, member_id)
    if m.deleted_at is not None:
        return m
    open_dates = list(db.scalars(
        select(ClubSession.session_date)
        .join(SessionMember, SessionMember.session_id == ClubSession.session_id)
        .where(SessionMember.member_id == member_id,
               SessionMember.attendance_status == AttendanceStatus.ATTENDING,
               ClubSession.club_id == club_id, ClubSession.deleted_at.is_(None),
               ClubSession.status.in_([SessionStatus.OPEN, SessionStatus.CONFIRMED, SessionStatus.IN_PROGRESS]))
        .order_by(ClubSession.session_date)))
    if open_dates:
        days = ", ".join(f"{d.month}/{d.day}" for d in open_dates)
        raise Conflict(f"{m.name} 선수는 아직 끝나지 않은 일정({days})에 참석으로 되어 있어요. 참석을 취소하거나 일정을 마감한 뒤 삭제하세요.",
                       "MEMBER_IN_OPEN_SESSION")
    now = utcnow()
    # MySQL DATETIME(3) 반올림 때문에 응답 시각과 재조회 시각이 달라지지 않게 밀리초로 맞춘다
    m.deleted_at = now.replace(microsecond=(now.microsecond // 1000) * 1000)
    db.commit()
    return m


def restore_member(db: Session, club_id: int, member_id: int) -> Member:
    """삭제 취소. 활동/비활성 상태는 삭제 전 그대로."""
    m = get_member(db, club_id, member_id)
    if m.deleted_at is not None:
        m.deleted_at = None
        db.commit()
    return m


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
    if m.deleted_at is not None:
        raise Conflict("삭제한 선수는 복원한 뒤 수정하세요.", "MEMBER_DELETED")
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
