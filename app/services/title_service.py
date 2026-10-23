"""타이틀(이주의 득점왕 / 도움왕, 이달의 MVP …) 정의와 수여 이력. 비활성 타이틀(예: 제거된 주간 MVP)의 지난 이력은 조회에서 제외.

이달의 MVP(MONTHLY)는 [일정마감]이 아니라 월 마감 때 mvp_service가 집계한다.
"""
from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.database import emit
from app.core.errors import BadRequest, Conflict, NotFound
from app.core.timeutil import month_range, to_iso, utcnow, week_range
from app.models import ClubSession, Member, MemberTitle, TitleType
from app.models.enums import AwardMethod, SessionStatus, TitleAutoRule, TitlePeriodType
from app.services.common import get_member, get_session, member_names
from app.services.history import load_history, member_totals
from app.services.stats_service import rebuild_member_stats


# ------------------------------------------------------------------ 정의
def list_title_types(db: Session, club_id: int, include_inactive: bool = False) -> list[TitleType]:
    stmt = select(TitleType).where(TitleType.club_id == club_id)
    if not include_inactive:
        stmt = stmt.where(TitleType.active_yn.is_(True))
    return list(db.scalars(stmt.order_by(TitleType.display_order, TitleType.title_type_id)))


def _validate_type_fields(period_type: str, award_method: str, auto_rule: str | None) -> None:
    if period_type not in TitlePeriodType.__members__:
        raise BadRequest("periodType은 WEEKLY/SESSION/MONTHLY 중 하나입니다.")
    if award_method not in AwardMethod.__members__:
        raise BadRequest("awardMethod는 MANUAL/AUTO 중 하나입니다.")
    weekly_rules = (TitleAutoRule.TOP_GOALS, TitleAutoRule.TOP_ASSISTS, TitleAutoRule.TOP_WINS)
    if award_method == AwardMethod.AUTO and (auto_rule not in weekly_rules or period_type == TitlePeriodType.MONTHLY):
        # MONTHLY_RATING_RISE(이달의 MVP)는 시스템 전용
        raise BadRequest("AUTO 타이틀은 주간/일정 단위 + autoRule(TOP_GOALS/TOP_ASSISTS/TOP_WINS)만 만들 수 있습니다.")


def create_title_type(db: Session, club_id: int, *, title_code: str, title_name: str, period_type: str = "WEEKLY",
                      award_method: str = "MANUAL", auto_rule: str | None = None, counts_as_mvp: bool = False,
                      display_order: int = 0) -> TitleType:
    _validate_type_fields(period_type, award_method, auto_rule)
    if db.scalar(select(TitleType).where(TitleType.club_id == club_id, TitleType.title_code == title_code)):
        raise Conflict("이미 있는 타이틀 코드입니다.", "TITLE_CODE_TAKEN")
    t = TitleType(club_id=club_id, title_code=title_code, title_name=title_name, period_type=period_type,
                  award_method=award_method, auto_rule=auto_rule if award_method == AwardMethod.AUTO else None,
                  counts_as_mvp_yn=counts_as_mvp, display_order=display_order)
    db.add(t)
    db.commit()
    return t


def update_title_type(db: Session, club_id: int, title_type_id: int, **fields) -> TitleType:
    t = db.scalar(select(TitleType).where(TitleType.title_type_id == title_type_id, TitleType.club_id == club_id))
    if not t:
        raise NotFound("타이틀을 찾을 수 없습니다.")
    for k in ("title_name", "active_yn", "display_order", "counts_as_mvp_yn"):
        if fields.get(k) is not None:
            setattr(t, k, fields[k])
    db.commit()
    return t


# ------------------------------------------------------------------ 수여
def _period(t: TitleType, d: date) -> tuple[date, date]:
    if t.period_type == TitlePeriodType.MONTHLY:
        return month_range(d)
    return week_range(d) if t.period_type == TitlePeriodType.WEEKLY else (d, d)


def award_title(db: Session, club_id: int, admin_id: int | None, *, title_code: str, member_id: int,
                award_date: date | None = None, session_id: int | None = None, note: str | None = None) -> MemberTitle:
    t = db.scalar(select(TitleType).where(TitleType.club_id == club_id, TitleType.title_code == title_code,
                                          TitleType.active_yn.is_(True)))
    if not t:
        raise NotFound("타이틀을 찾을 수 없습니다.", "TITLE_NOT_FOUND")
    if t.award_method != AwardMethod.MANUAL:
        raise BadRequest("자동 집계 타이틀은 직접 수여할 수 없습니다.", "AUTO_TITLE")
    get_member(db, club_id, member_id)
    s = get_session(db, club_id, session_id) if session_id else None
    d = s.session_date if s else award_date
    if d is None:
        raise BadRequest("sessionId 또는 awardDate가 필요합니다.")
    if t.period_type == TitlePeriodType.SESSION and not s:
        raise BadRequest("일정 단위 타이틀은 sessionId가 필요합니다.")
    start, end = _period(t, d)
    dup = db.scalar(select(MemberTitle).where(MemberTitle.title_type_id == t.title_type_id,
                                              MemberTitle.member_id == member_id, MemberTitle.period_start == start,
                                              MemberTitle.cancelled_yn.is_(False)))
    if dup:
        raise Conflict("이미 같은 기간에 수여된 타이틀입니다.", "ALREADY_AWARDED")
    mt = MemberTitle(club_id=club_id, title_type_id=t.title_type_id, member_id=member_id, period_start=start,
                     period_end=end, session_id=s.session_id if s else None, award_method=AwardMethod.MANUAL,
                     note=note, admin_id=admin_id)
    db.add(mt)
    db.flush()
    rebuild_member_stats(db, club_id)
    emit(db, club_id, "TITLE_UPDATED", {"memberTitleId": mt.member_title_id})
    db.commit()
    return mt


def cancel_award(db: Session, club_id: int, member_title_id: int) -> MemberTitle:
    mt = db.scalar(select(MemberTitle).where(MemberTitle.member_title_id == member_title_id,
                                             MemberTitle.club_id == club_id))
    if not mt:
        raise NotFound("수여 이력을 찾을 수 없습니다.")
    if mt.cancelled_yn:
        raise Conflict("이미 취소된 수여입니다.")
    mt.cancelled_yn = True
    mt.cancelled_at = utcnow()
    db.flush()
    rebuild_member_stats(db, club_id)
    emit(db, club_id, "TITLE_UPDATED", {"memberTitleId": mt.member_title_id})
    db.commit()
    return mt


def compute_auto_titles(db: Session, club_id: int, anchor: ClubSession) -> list[MemberTitle]:
    """[일정마감] 시 anchor 일정이 속한 기간의 자동 타이틀을 다시 계산한다(호출 측 트랜잭션).

    기간 안의 '마감된' 일정 + anchor 일정의 확정 경기만 집계. 동점자는 공동 수여.
    """
    created: list[MemberTitle] = []
    for t in list_title_types(db, club_id):
        if t.award_method != AwardMethod.AUTO or t.period_type == TitlePeriodType.MONTHLY:
            continue  # 이달의 MVP는 월 마감 때(mvp_service.close_month)
        start, end = _period(t, anchor.session_date)
        sids = list(db.scalars(select(ClubSession.session_id).where(
            ClubSession.club_id == club_id, ClubSession.session_date.between(start, end),
            (ClubSession.status == SessionStatus.CLOSED) | (ClubSession.session_id == anchor.session_id))))
        totals = member_totals(load_history(db, club_id, session_ids=sids)) if sids else {}
        metric = {TitleAutoRule.TOP_GOALS: "goals", TitleAutoRule.TOP_ASSISTS: "assists",
                  TitleAutoRule.TOP_WINS: "wins"}[TitleAutoRule(t.auto_rule)]
        best = max((getattr(v, metric) for v in totals.values()), default=0)
        winners = sorted(mid for mid, v in totals.items() if best > 0 and getattr(v, metric) == best)

        existing = list(db.scalars(select(MemberTitle).where(
            MemberTitle.title_type_id == t.title_type_id, MemberTitle.period_start == start,
            MemberTitle.cancelled_yn.is_(False), MemberTitle.award_method == AwardMethod.AUTO)))
        if sorted(e.member_id for e in existing) == winners and all(
                (e.facts_json or {}).get("value") == best for e in existing):
            created.extend(existing)
            continue
        for e in existing:
            e.cancelled_yn = True
            e.cancelled_at = utcnow()
        for mid in winners:
            mt = MemberTitle(club_id=club_id, title_type_id=t.title_type_id, member_id=mid, period_start=start,
                             period_end=end, session_id=anchor.session_id, award_method=AwardMethod.AUTO,
                             facts_json={"metric": metric, "value": best, "tied": len(winners) > 1})
            db.add(mt)
            created.append(mt)
    db.flush()
    return created


def list_awards(db: Session, club_id: int, *, member_id: int | None = None, date_from: date | None = None,
                date_to: date | None = None, include_cancelled: bool = False, limit: int = 100) -> list[dict]:
    stmt = (select(MemberTitle, TitleType).join(TitleType, TitleType.title_type_id == MemberTitle.title_type_id)
            .where(MemberTitle.club_id == club_id, TitleType.active_yn.is_(True)))  # 비활성 타이틀 이력은 숨김
    if member_id:
        stmt = stmt.where(MemberTitle.member_id == member_id)
    if date_from:
        stmt = stmt.where(MemberTitle.period_end >= date_from)
    if date_to:
        stmt = stmt.where(MemberTitle.period_start <= date_to)
    if not include_cancelled:
        stmt = stmt.where(MemberTitle.cancelled_yn.is_(False))
    rows = db.execute(stmt.order_by(MemberTitle.period_start.desc(), TitleType.display_order).limit(limit)).all()
    names = member_names(db, [mt.member_id for mt, _ in rows])
    return [
        {"memberTitleId": mt.member_title_id, "titleCode": t.title_code, "titleName": t.title_name,
         "memberId": mt.member_id, "memberName": names.get(mt.member_id), "periodStart": mt.period_start,
         "periodEnd": mt.period_end, "sessionId": mt.session_id, "awardMethod": mt.award_method,
         "facts": mt.facts_json, "note": mt.note, "cancelled": mt.cancelled_yn, "createdAt": to_iso(mt.created_at)}
        for mt, t in rows
    ]


__all__ = ["list_title_types", "create_title_type", "update_title_type", "award_title", "cancel_award",
           "compute_auto_titles", "list_awards", "Member"]
