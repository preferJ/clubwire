"""클럽 생성/관리자 인증."""
from datetime import date

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.errors import BadRequest, Conflict, Unauthorized
from app.core.security import create_admin_token, hash_password, login_limiter, verify_password
from app.core.timeutil import utcnow
from app.models import AiArticle, Club, ClubAdmin, ClubSession, Member, TitleType
from app.models.enums import AwardMethod, SessionStatus, TitleAutoRule, TitlePeriodType
from app.services.config_service import seed_club_config
from app.wire.insight_types import ensure_insight_types

DEFAULT_TITLES = (
    # code, name, period, method, auto_rule, counts_as_mvp  (MVP는 2026-10-22 제거: alembic 0004)
    ("TOP_SCORER", "이주의 득점왕", TitlePeriodType.WEEKLY, AwardMethod.AUTO, TitleAutoRule.TOP_GOALS, False),
    ("TOP_ASSIST", "이주의 도움왕", TitlePeriodType.WEEKLY, AwardMethod.AUTO, TitleAutoRule.TOP_ASSISTS, False),
)


def validate_pin(pin: str) -> None:
    if not pin or len(pin) < 4 or len(pin) > 64:
        raise BadRequest("관리자 암호는 4자 이상이어야 합니다.", "INVALID_PIN")


def create_club(db: Session, slug: str, name: str, admin_pin: str, sport_type: str = "FUTSAL",
                timezone: str = "Asia/Seoul") -> Club:
    validate_pin(admin_pin)
    if db.scalar(select(Club).where(Club.club_slug == slug)):
        raise Conflict(f"이미 사용 중인 클럽 주소입니다: {slug}", "SLUG_TAKEN")
    ensure_insight_types(db)
    club = Club(club_slug=slug, club_name=name, sport_type=sport_type, timezone=timezone)
    db.add(club)
    db.flush()
    db.add(ClubAdmin(club_id=club.club_id, admin_name="owner", password_hash=hash_password(admin_pin)))
    seed_club_config(db, club.club_id)
    for i, (code, tname, period, method, rule, mvp) in enumerate(DEFAULT_TITLES):
        db.add(TitleType(club_id=club.club_id, title_code=code, title_name=tname, period_type=period,
                         award_method=method, auto_rule=rule, counts_as_mvp_yn=mvp, display_order=i))
    db.commit()
    return club


def set_admin_pin(db: Session, club_id: int, new_pin: str) -> None:
    validate_pin(new_pin)
    admins = list(db.scalars(select(ClubAdmin).where(ClubAdmin.club_id == club_id, ClubAdmin.active_yn.is_(True))))
    if admins:
        admins[0].password_hash = hash_password(new_pin)
    else:
        db.add(ClubAdmin(club_id=club_id, admin_name="owner", password_hash=hash_password(new_pin)))
    db.commit()


def admin_login(db: Session, club: Club, pin: str, client_key: str) -> tuple[str, object]:
    key = f"{club.club_id}:{client_key}"
    login_limiter.check(key)
    admins = db.scalars(select(ClubAdmin).where(ClubAdmin.club_id == club.club_id, ClubAdmin.active_yn.is_(True)))
    for admin in admins:
        if verify_password(admin.password_hash, pin):
            login_limiter.success(key)
            admin.last_login_at = utcnow()
            db.commit()
            return create_admin_token(club.club_id, admin.admin_id)
    login_limiter.fail(key)
    raise Unauthorized("관리자 암호가 올바르지 않습니다.", "INVALID_PIN")


def club_summary(db: Session, club: Club, today: date) -> dict:
    """와이어 상단 요약 줄: 활동 멤버 수 · 올해 일정 수(취소 제외) · 올해 일정의 게시 기사 수."""
    start, end = date(today.year, 1, 1), date(today.year, 12, 31)
    members = db.scalar(select(func.count()).select_from(Member)
                        .where(Member.club_id == club.club_id, Member.active_yn.is_(True)))
    sessions = db.scalar(select(func.count()).select_from(ClubSession)
                         .where(ClubSession.club_id == club.club_id, ClubSession.status != SessionStatus.CANCELLED,
                                ClubSession.session_date.between(start, end)))
    articles = db.scalar(select(func.count()).select_from(AiArticle)
                         .join(ClubSession, ClubSession.session_id == AiArticle.session_id)
                         .where(AiArticle.club_id == club.club_id, AiArticle.published_yn.is_(True),
                                ClubSession.session_date.between(start, end)))
    return {"year": today.year, "activeMembers": members or 0, "sessions": sessions or 0, "articles": articles or 0}
