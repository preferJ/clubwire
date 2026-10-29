"""전역 슈퍼관리자의 운영팀 관리. 기존 CLUB_ID와 소속 기록을 유지한다."""
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.database import emit
from app.core.errors import BadRequest, Conflict, NotFound
from app.core.security import hash_password
from app.models import AiArticle, Club, ClubAdmin, ClubSession, Member
from app.services import club_service


def _validate_timezone(value: str) -> None:
    try:
        ZoneInfo(value)
    except (ZoneInfoNotFoundError, ValueError) as exc:
        raise BadRequest("올바른 시간대를 입력하세요(예: Asia/Seoul).", "INVALID_TIMEZONE") from exc


def _get_club(db: Session, club_id: int, *, lock: bool = False) -> Club:
    stmt = select(Club).where(Club.club_id == club_id)
    if lock:
        stmt = stmt.with_for_update()
    club = db.scalar(stmt)
    if club is None:
        raise NotFound("팀을 찾을 수 없습니다.", "CLUB_NOT_FOUND")
    return club


def _count_by_club(db: Session, model, *conditions) -> dict[int, int]:
    return dict(db.execute(select(model.club_id, func.count()).where(*conditions).group_by(model.club_id)).all())


def list_clubs(db: Session) -> list[dict[str, Any]]:
    # 팀 수에 비례해 쿼리가 늘지 않도록 각 집계를 한 번씩 조회한다.
    members = _count_by_club(db, Member)
    sessions = _count_by_club(db, ClubSession, ClubSession.deleted_at.is_(None))
    articles = _count_by_club(db, AiArticle)
    return [_serialize(club, members.get(club.club_id, 0), sessions.get(club.club_id, 0),
                       articles.get(club.club_id, 0))
            for club in db.scalars(select(Club).order_by(Club.club_id))]


def _serialize(club: Club, member_count: int, session_count: int, article_count: int) -> dict[str, Any]:
    return {
        "clubId": club.club_id, "clubSlug": club.club_slug, "clubName": club.club_name,
        "sportType": club.sport_type, "timezone": club.timezone, "active": club.active_yn,
        "memberCount": member_count, "sessionCount": session_count, "articleCount": article_count,
    }


def club_detail(db: Session, club: Club) -> dict[str, Any]:
    cid = club.club_id
    members = db.scalar(select(func.count()).select_from(Member).where(Member.club_id == cid)) or 0
    sessions = db.scalar(select(func.count()).select_from(ClubSession).where(
        ClubSession.club_id == cid, ClubSession.deleted_at.is_(None))) or 0
    articles = db.scalar(select(func.count()).select_from(AiArticle).where(AiArticle.club_id == cid)) or 0
    return _serialize(club, members, sessions, articles)


def create_club(db: Session, **values) -> dict[str, Any]:
    _validate_timezone(values["timezone"])
    try:
        club = club_service.create_club(
            db, values["club_slug"], values["club_name"], values["admin_pin"],
            sport_type=values["sport_type"], timezone=values["timezone"],
        )
    except IntegrityError as exc:
        db.rollback()
        raise Conflict("이미 사용 중인 팀 주소입니다.", "SLUG_TAKEN") from exc
    return club_detail(db, club)


def update_club(db: Session, club_id: int, values: dict[str, Any]) -> dict[str, Any]:
    if not values or any(value is None for value in values.values()):
        raise BadRequest("변경할 값을 입력하세요. 빈 값(null)은 허용하지 않습니다.", "INVALID_CLUB_UPDATE")
    if "timezone" in values:
        _validate_timezone(values["timezone"])
    try:
        club = _get_club(db, club_id, lock=True)
        slug = values.get("club_slug")
        if slug is not None and db.scalar(select(Club.club_id).where(
                Club.club_slug == slug, Club.club_id != club_id)) is not None:
            raise Conflict("이미 사용 중인 팀 주소입니다.", "SLUG_TAKEN")
        for key in ("club_slug", "club_name", "timezone"):
            if key in values:
                setattr(club, key, values[key])
        if "admin_pin" in values:
            password_hash = hash_password(values["admin_pin"])
            # PIN 변경 시 현재 활성 관리자 계정들의 암호를 함께 변경한다.
            admins = list(db.scalars(select(ClubAdmin).where(
                ClubAdmin.club_id == club_id, ClubAdmin.active_yn.is_(True)).with_for_update()))
            if admins:
                for admin in admins:
                    admin.password_hash = password_hash
            else:
                db.add(ClubAdmin(club_id=club_id, admin_name="owner", password_hash=password_hash))
        db.commit()
        return club_detail(db, club)
    except IntegrityError as exc:
        db.rollback()
        raise Conflict("이미 사용 중인 팀 주소입니다.", "SLUG_TAKEN") from exc
    except Exception:
        db.rollback()
        raise


def set_club_active(db: Session, club_id: int, active: bool) -> dict[str, Any]:
    """제거는 접근 중지만 한다. 팀 ID와 모든 소속 기록·관리자 계정을 보존한다."""
    club = _get_club(db, club_id, lock=True)
    if club.active_yn != active:
        club.active_yn = active
        if not active:
            # 이미 열려 있던 해당 팀의 WebSocket도 커밋 이후 닫는다.
            emit(db, club_id, "CLUB_DEACTIVATED", {})
    db.commit()
    return club_detail(db, club)
