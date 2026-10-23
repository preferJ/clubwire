"""일정 생명주기: [일정확정] / [일정마감] / 전체 재계산.

[일정확정] = 팀 확정 → PRE Insight → PRE_MATCH 기사(1건)
    이후 [일정마감]까지 기사를 만들지 않는다.
[일정마감] = 남은 경기 정리/확정 → 자동 타이틀 → 통계 → POST Insight → SESSION_RECAP 기사(1건)
    마감된 일정의 팀/경기/골은 수정 불가.
    마감은 날짜 순서대로만 가능(앞 일정이 열려 있으면 거부) → 마감된 기록 이후의 Rating이 흔들리지 않는다.
"""
from sqlalchemy import select, tuple_
from sqlalchemy.orm import Session

from app.core.database import emit
from app.core.errors import Conflict
from app.core.timeutil import utcnow
from app.models import Club, ClubSession
from app.models.enums import ArticleType, RatingChangeReason, SessionStatus
from app.services.common import get_session, guard_not_closed
from app.services.match_service import finalize_remaining_for_close
from app.services.rating_service import rebuild_ratings
from app.services.stats_service import rebuild_all_stats
from app.services.team_service import apply_generation
from app.services.title_service import compute_attendance_titles, compute_auto_titles
from app.wire.article_service import create_article
from app.wire.insight_engine import generate_post_insights, generate_pre_insights, session_summary


def confirm_session(db: Session, club_id: int, session_id: int, generation_id: int,
                    admin_id: int | None) -> tuple[ClubSession, list[int]]:
    s = get_session(db, club_id, session_id, lock=True)
    guard_not_closed(s)
    if s.status != SessionStatus.OPEN:
        raise Conflict("이미 확정된 일정입니다.", "SESSION_CONFIRMED")
    apply_generation(db, s, generation_id)
    insights = generate_pre_insights(db, club_id, s)
    club = db.get(Club, club_id)
    article = create_article(db, club, s, ArticleType.PRE_MATCH, insights)
    emit(db, club_id, "SESSION_UPDATED", {"sessionId": s.session_id, "status": s.status})
    emit(db, club_id, "TEAMS_UPDATED", {"sessionId": s.session_id})
    db.commit()
    return s, [article.article_id]


def close_session(db: Session, club_id: int, session_id: int, admin_id: int | None) -> tuple[ClubSession, list[int]]:
    s = get_session(db, club_id, session_id, lock=True)
    guard_not_closed(s)
    if s.status not in (SessionStatus.CONFIRMED, SessionStatus.IN_PROGRESS):
        raise Conflict("팀이 확정되지 않은 일정은 마감할 수 없습니다. 취소를 사용하세요.", "SESSION_NOT_CONFIRMED")
    earlier = list(db.scalars(select(ClubSession).where(
        ClubSession.club_id == club_id,
        tuple_(ClubSession.session_date, ClubSession.session_id) < tuple_(s.session_date, s.session_id),
        ClubSession.status.not_in([SessionStatus.CLOSED, SessionStatus.CANCELLED]))))
    if earlier:
        dates = ", ".join(f"{x.session_date}(#{x.session_id})" for x in earlier)
        raise Conflict(f"앞선 일정을 먼저 마감하거나 취소하세요: {dates}", "PREVIOUS_SESSION_OPEN")

    finalized_count = finalize_remaining_for_close(db, club_id, s, admin_id)
    s.status = SessionStatus.CLOSED
    s.closed_at = utcnow()
    db.flush()
    compute_auto_titles(db, club_id, s)
    compute_attendance_titles(db, club_id, s)  # 연속 참가 10 · 20 · 30 · 40 · 50회
    rebuild_all_stats(db, club_id)
    article_ids: list[int] = []
    if finalized_count:
        insights = generate_post_insights(db, club_id, s)
        club = db.get(Club, club_id)
        article = create_article(db, club, s, ArticleType.SESSION_RECAP, insights,
                                 {"sessionSummary": session_summary(db, club_id, s)})
        article_ids.append(article.article_id)
    emit(db, club_id, "SESSION_UPDATED", {"sessionId": s.session_id, "status": s.status})
    db.commit()
    return s, article_ids


def rebuild_everything(db: Session, club_id: int) -> dict:
    """관리자용 전체 재계산(Rating 전 구간 재생 + 통계 + Pair)."""
    n = rebuild_ratings(db, club_id, None, RatingChangeReason.ADMIN_RECALC)
    rebuild_all_stats(db, club_id)
    db.commit()
    return {"replayedMatches": n}
