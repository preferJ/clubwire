"""서비스 공통 조회/검증."""
from collections.abc import Iterable

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import Conflict, NotFound
from app.models import Club, ClubSession, MatchGame, Member, SessionTeam
from app.models.enums import SessionStatus


def get_club_by_slug(db: Session, slug: str) -> Club:
    club = db.scalar(select(Club).where(Club.club_slug == slug, Club.active_yn.is_(True)))
    if not club:
        raise NotFound("클럽을 찾을 수 없습니다.", "CLUB_NOT_FOUND")
    return club


def lock_club(db: Session, club_id: int) -> Club:
    """파생 데이터 재계산을 클럽 단위로 직렬화하기 위한 행 잠금."""
    return db.execute(select(Club).where(Club.club_id == club_id).with_for_update()).scalar_one()


def get_session(db: Session, club_id: int, session_id: int, *, lock: bool = False) -> ClubSession:
    stmt = select(ClubSession).where(ClubSession.session_id == session_id, ClubSession.club_id == club_id)
    if lock:
        stmt = stmt.with_for_update()
    s = db.scalar(stmt)
    if not s:
        raise NotFound("일정을 찾을 수 없습니다.", "SESSION_NOT_FOUND")
    return s


def get_match(db: Session, club_id: int, match_id: int, *, lock: bool = False) -> tuple[MatchGame, ClubSession]:
    stmt = (
        select(MatchGame, ClubSession)
        .join(ClubSession, ClubSession.session_id == MatchGame.session_id)
        .where(MatchGame.match_id == match_id, ClubSession.club_id == club_id)
    )
    if lock:
        stmt = stmt.with_for_update(of=MatchGame)
    row = db.execute(stmt).first()
    if not row:
        raise NotFound("경기를 찾을 수 없습니다.", "MATCH_NOT_FOUND")
    return row[0], row[1]


def get_member(db: Session, club_id: int, member_id: int, *, active_only: bool = False) -> Member:
    m = db.scalar(select(Member).where(Member.member_id == member_id, Member.club_id == club_id))
    if not m or (active_only and not m.active_yn):
        raise NotFound(f"멤버({member_id})를 찾을 수 없습니다.", "MEMBER_NOT_FOUND")
    return m


def guard_not_closed(session: ClubSession) -> None:
    if session.status == SessionStatus.CLOSED:
        raise Conflict("마감된 일정은 수정할 수 없습니다.", "SESSION_CLOSED")
    if session.status == SessionStatus.CANCELLED:
        raise Conflict("취소된 일정입니다.", "SESSION_CANCELLED")


def member_names(db: Session, member_ids: Iterable[int]) -> dict[int, str]:
    ids = {i for i in member_ids if i is not None}
    if not ids:
        return {}
    return {m.member_id: m.name for m in db.scalars(select(Member).where(Member.member_id.in_(ids)))}


def session_teams(db: Session, session_id: int) -> list[SessionTeam]:
    return list(
        db.scalars(
            select(SessionTeam)
            .where(SessionTeam.session_id == session_id)
            .order_by(SessionTeam.display_order, SessionTeam.team_code)
        )
    )


def session_order_key(s: ClubSession) -> tuple:
    return (s.session_date, s.session_id)


def last_closed_key(db: Session, club_id: int) -> tuple | None:
    """가장 늦게 마감된 일정의 (날짜, ID). 이보다 앞선 시점의 기록은 더 생기면 안 된다."""
    row = db.execute(
        select(ClubSession.session_date, ClubSession.session_id)
        .where(ClubSession.club_id == club_id, ClubSession.status == SessionStatus.CLOSED)
        .order_by(ClubSession.session_date.desc(), ClubSession.session_id.desc())
        .limit(1)
    ).first()
    return (row[0], row[1]) if row else None


def guard_after_closed(db: Session, club_id: int, key: tuple) -> None:
    """마감된 일정보다 앞선 날짜에 기록이 생기면 마감된 구간의 Rating이 다시 바뀌므로 막는다."""
    closed = last_closed_key(db, club_id)
    if closed and key <= closed:
        raise Conflict(f"마감된 일정({closed[0]}) 이전 날짜에는 기록할 수 없습니다.", "BEFORE_CLOSED_SESSION")
