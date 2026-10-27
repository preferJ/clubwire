"""클럽 생성/관리자 인증."""
import re
from datetime import date, datetime, time, timezone

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.errors import BadRequest, Conflict, NotFound, Unauthorized
from app.core.security import create_admin_token, hash_password, login_limiter, verify_password
from app.core.timeutil import club_tz, utcnow
from app.models import AiArticle, Club, ClubAdmin, ClubSession, Member, TitleType
from app.models.enums import AwardMethod, SessionStatus, TitleAutoRule, TitlePeriodType
from app.services.config_service import seed_club_config
from app.wire.insight_types import ensure_insight_types

DEFAULT_TITLES = (
    # code, name, period, method, auto_rule, counts_as_mvp  (MVP는 2026-10-22 제거: alembic 0004)
    ("TOP_SCORER", "이주의 득점왕", TitlePeriodType.WEEKLY, AwardMethod.AUTO, TitleAutoRule.TOP_GOALS, False),
    ("TOP_ASSIST", "이주의 도움왕", TitlePeriodType.WEEKLY, AwardMethod.AUTO, TitleAutoRule.TOP_ASSISTS, False),
    # 이달의 MVP: 월 마감 때 실력 점수 상승률 1위(mvp_service). 기존 클럽은 첫 월 마감 때 자동으로 만들어짐
    ("MONTHLY_MVP", "이달의 MVP", TitlePeriodType.MONTHLY, AwardMethod.AUTO, TitleAutoRule.MONTHLY_RATING_RISE, True),
    # 이달의 득점왕 · 도움왕(월 마감) / 연속 참가 n회([일정마감]). 기존 클럽은 처음 필요할 때 자동으로 만들어짐
    ("MONTHLY_TOP_SCORER", "이달의 득점왕", TitlePeriodType.MONTHLY, AwardMethod.AUTO, TitleAutoRule.TOP_GOALS, False),
    ("MONTHLY_TOP_ASSIST", "이달의 도움왕", TitlePeriodType.MONTHLY, AwardMethod.AUTO, TitleAutoRule.TOP_ASSISTS, False),
    *((f"ATTEND_STREAK_{n}", f"연속 참가 {n}회", TitlePeriodType.SESSION, AwardMethod.AUTO, TitleAutoRule.ATTENDANCE_STREAK,
       False) for n in (10, 20, 30, 40, 50)),
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


def rename_club(db: Session, old_slug: str, new_slug: str, new_name: str | None = None) -> Club:
    """클럽 ID와 모든 기록을 유지하고 주소/표시 이름만 변경한다."""
    if not re.fullmatch(r"[a-z0-9_-]{1,50}", new_slug):
        raise BadRequest("클럽 주소는 영문 소문자, 숫자, - 또는 _로 1~50자 입력하세요.", "INVALID_SLUG")
    if new_name is not None:
        new_name = new_name.strip()
        if not 1 <= len(new_name) <= 100:
            raise BadRequest("클럽 이름은 1~100자 입력하세요.", "INVALID_CLUB_NAME")

    try:
        clubs = list(db.scalars(
            select(Club).where(Club.club_slug.in_({old_slug, new_slug}))
            .order_by(Club.club_id).with_for_update().execution_options(populate_existing=True)
        ))
        club = next((c for c in clubs if c.club_slug == old_slug), None)
        if club is None:
            raise NotFound("클럽을 찾을 수 없습니다.", "CLUB_NOT_FOUND")
        if any(c.club_slug == new_slug and c.club_id != club.club_id for c in clubs):
            raise Conflict(f"이미 사용 중인 클럽 주소입니다: {new_slug}", "SLUG_TAKEN")
        club.club_slug = new_slug
        if new_name is not None:
            club.club_name = new_name
        db.commit()
        return club
    except IntegrityError as exc:
        # 확인 직후 다른 트랜잭션이 같은 주소를 선점한 경우에도 변경을 남기지 않는다.
        db.rollback()
        raise Conflict(f"이미 사용 중인 클럽 주소입니다: {new_slug}", "SLUG_TAKEN") from exc
    except Exception:
        db.rollback()
        raise


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
    """와이어 상단 요약 줄: 활동 멤버 수 · 올해 일정 수(취소 제외) · 올해 일정의 게시 기사와 올해 게시된 공지 수."""
    start, end = date(today.year, 1, 1), date(today.year, 12, 31)
    members = db.scalar(select(func.count()).select_from(Member)
                        .where(Member.club_id == club.club_id, Member.active_yn.is_(True)))
    sessions = db.scalar(select(func.count()).select_from(ClubSession)
                         .where(ClubSession.club_id == club.club_id, ClubSession.status != SessionStatus.CANCELLED,
                                ClubSession.session_date.between(start, end), ClubSession.deleted_at.is_(None)))
    year_start = datetime.combine(start, time.min, club_tz(club.timezone)).astimezone(timezone.utc).replace(tzinfo=None)
    year_end = datetime.combine(date(today.year + 1, 1, 1), time.min, club_tz(club.timezone)).astimezone(timezone.utc).replace(tzinfo=None)
    articles = db.scalar(select(func.count()).select_from(AiArticle)
                         .outerjoin(ClubSession, ClubSession.session_id == AiArticle.session_id)
                         .where(AiArticle.club_id == club.club_id, AiArticle.published_yn.is_(True),
                                ((ClubSession.session_date.between(start, end) & ClubSession.deleted_at.is_(None))
                                 | (AiArticle.session_id.is_(None) & (AiArticle.published_at >= year_start)
                                    & (AiArticle.published_at < year_end)))))
    return {"year": today.year, "activeMembers": members or 0, "sessions": sessions or 0, "articles": articles or 0}
