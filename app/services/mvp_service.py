"""이달의 MVP: 그 달 실력 점수(Rating) 상승률 1위를 월 마감 때 자동 선정.

- 상승률 = (그 달 마지막 경기 후 점수 - 그 달 첫 경기 전 점수) ÷ 첫 경기 전 점수 × 100
  점수는 PLAYER_RATING_HISTORY(무효 처리 안 된 경기 이력)에서 읽는다. 화면·API·기사에는 상승률(%)만 내보내고
  점수 자체는 내보내지 않는다(Rating은 DB에서만).
- 후보 자격: 그 달 출전 일정 수 >= MONTHLY_MVP_MIN_SESSIONS(기본 2) 이고 상승률 > 0
- 월 마감: 클럽 현지 날짜로 다음 달이 되고, 그 달 일정이 모두 마감/취소되면
  → MEMBER_TITLE(이달의 MVP) 수여 + MONTHLY_MVP 기사 작성(게시 설정과 상관없이 바로 게시)
- 한 달은 한 번만 마감한다(수여 이력이 있으면 관리자가 취소한 것이라도 다시 만들지 않음).
"""
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.database import emit
from app.core.timeutil import local_today, month_range, prev_month_start
from app.models import AiArticle, Club, ClubSession, MatchGame, MemberTitle, PlayerRatingHistory, SessionTeam, TitleType
from app.models.enums import (
    ArticleType,
    AwardMethod,
    ReferenceType,
    SessionStatus,
    TitleAutoRule,
    TitlePeriodType,
)
from app.services.common import lock_club, member_names
from app.services.config_service import load_config
from app.services.history import load_history
from app.services.stats_service import rebuild_member_stats
from app.wire.article_service import create_article

MVP_CODE = "MONTHLY_MVP"
MVP_NAME = "이달의 MVP"
RACE_SIZE = 3  # 홈 화면 후보 수


@dataclass
class _Step:
    """한 경기에서의 점수 변화(이력 1행)."""
    match_id: int
    session_id: int
    session_date: date
    game_no: int
    before: float
    change: float


@dataclass
class MonthRise:
    member_id: int
    steps: list[_Step] = field(default_factory=list)

    @property
    def start(self) -> float:
        return self.steps[0].before

    @property
    def end(self) -> float:
        return self.steps[-1].before + self.steps[-1].change

    @property
    def percent(self) -> float:
        return round((self.end - self.start) / self.start * 100, 2) if self.start else 0.0

    @property
    def sessions(self) -> int:
        return len({s.session_id for s in self.steps})

    @property
    def games(self) -> int:
        return len(self.steps)


def month_rises(db: Session, club_id: int, start: date, end: date) -> dict[int, MonthRise]:
    """기간 안 확정 경기의 점수 변화를 선수별로(경기 순서대로) 모은다."""
    rows = db.execute(
        select(PlayerRatingHistory, MatchGame.game_no, ClubSession.session_id, ClubSession.session_date)
        .join(MatchGame, MatchGame.match_id == PlayerRatingHistory.reference_id)
        .join(ClubSession, ClubSession.session_id == MatchGame.session_id)
        .where(
            PlayerRatingHistory.club_id == club_id,
            PlayerRatingHistory.voided_yn.is_(False),
            PlayerRatingHistory.reference_type == ReferenceType.MATCH,
            ClubSession.status != SessionStatus.CANCELLED,
            ClubSession.session_date.between(start, end),
        )
        .order_by(ClubSession.session_date, ClubSession.session_id, MatchGame.game_no,
                  PlayerRatingHistory.rating_history_id)
    ).all()
    out: dict[int, MonthRise] = {}
    for h, game_no, sid, sdate in rows:
        out.setdefault(h.member_id, MonthRise(h.member_id)).steps.append(
            _Step(int(h.reference_id), sid, sdate, game_no, h.before_rating, h.change_amount))
    return out


def ranking(db: Session, club_id: int, start: date, end: date, min_sessions: int) -> list[MonthRise]:
    """후보(자격 충족 + 상승) 상승률 높은 순. 같으면 경기 수 많은 순."""
    rises = [r for r in month_rises(db, club_id, start, end).values() if r.sessions >= min_sessions and r.percent > 0]
    return sorted(rises, key=lambda r: (-r.percent, -r.games, r.member_id))


def _candidates(db: Session, ranked: list[MonthRise]) -> list[dict]:
    names = member_names(db, [r.member_id for r in ranked])
    out, rank = [], 0
    for i, r in enumerate(ranked):
        if i == 0 or r.percent != ranked[i - 1].percent:
            rank = i + 1
        out.append({"rank": rank, "memberId": r.member_id, "name": names.get(r.member_id),
                    "risePercent": r.percent, "sessions": r.sessions, "games": r.games})
    return out


def _mvp_type(db: Session, club_id: int, create: bool = False) -> TitleType | None:
    """'이달의 MVP' 타이틀 정의. 없으면(기존 클럽 · 샘플 데이터 복원 후) 만든다. 관리자가 비활성화했으면 None."""
    t = db.scalar(select(TitleType).where(TitleType.club_id == club_id, TitleType.title_code == MVP_CODE))
    if t is None and create:
        t = TitleType(club_id=club_id, title_code=MVP_CODE, title_name=MVP_NAME, period_type=TitlePeriodType.MONTHLY,
                      award_method=AwardMethod.AUTO, auto_rule=TitleAutoRule.MONTHLY_RATING_RISE,
                      counts_as_mvp_yn=True, display_order=2)
        db.add(t)
        db.flush()
    return t if t is not None and t.active_yn else None


def mvp_race(db: Session, club: Club, today: date | None = None) -> dict:
    """홈 화면: 이번 달 후보 1~3위(상승률만) + 지난달 MVP."""
    today = today or local_today(club.timezone)
    start, end = month_range(today)
    min_sessions = int(load_config(db, club.club_id)["MONTHLY_MVP_MIN_SESSIONS"])
    ranked = ranking(db, club.club_id, start, end, min_sessions)[:RACE_SIZE]
    return {"month": start.strftime("%Y-%m"), "minSessions": min_sessions, "candidates": _candidates(db, ranked),
            "lastMonth": _last_month(db, club.club_id, prev_month_start(today))}


def _last_month(db: Session, club_id: int, month_start: date) -> dict | None:
    t = _mvp_type(db, club_id)
    if not t:
        return None
    titles = list(db.scalars(select(MemberTitle).where(
        MemberTitle.title_type_id == t.title_type_id, MemberTitle.period_start == month_start,
        MemberTitle.cancelled_yn.is_(False)).order_by(MemberTitle.member_title_id)))
    if not titles:
        return None
    names = member_names(db, [x.member_id for x in titles])
    article_id = db.scalar(select(AiArticle.article_id).where(
        AiArticle.club_id == club_id, AiArticle.session_id == titles[0].session_id,
        AiArticle.article_type == ArticleType.MONTHLY_MVP, AiArticle.published_yn.is_(True)))
    return {"month": month_start.strftime("%Y-%m"), "articleId": article_id,
            "winners": [{"memberId": x.member_id, "name": names.get(x.member_id),
                         "risePercent": (x.facts_json or {}).get("value")} for x in titles]}


# ------------------------------------------------------------------ 월 마감
def close_due_month(db: Session, club: Club, today: date | None = None) -> list[int]:
    """지난달 마감이 가능하면 마감한다. 반환: 새로 만든 기사 ID(호출 측이 생성 실행)."""
    today = today or local_today(club.timezone)
    return close_month(db, club, prev_month_start(today))


def close_month(db: Session, club: Club, month_start: date) -> list[int]:
    start, end = month_range(month_start)
    lock_club(db, club.club_id)
    t = _mvp_type(db, club.club_id, create=True)
    if not t:
        db.rollback()
        return []
    done = db.scalar(select(MemberTitle.member_title_id).where(
        MemberTitle.title_type_id == t.title_type_id, MemberTitle.period_start == start).limit(1))
    sessions = list(db.scalars(select(ClubSession).where(
        ClubSession.club_id == club.club_id, ClubSession.session_date.between(start, end),
        ClubSession.status != SessionStatus.CANCELLED).order_by(ClubSession.session_date, ClubSession.session_id)))
    # 이미 마감 / 일정 없음 / 아직 안 끝난 일정이 있음 → 다음에 다시 확인
    if done or not sessions or any(s.status != SessionStatus.CLOSED for s in sessions):
        db.commit()  # 타이틀 정의를 새로 만들었으면 저장
        return []
    min_sessions = int(load_config(db, club.club_id)["MONTHLY_MVP_MIN_SESSIONS"])
    ranked = ranking(db, club.club_id, start, end, min_sessions)
    if not ranked:
        db.commit()
        return []

    anchor = sessions[-1]  # 기사는 그 달 마지막 일정에 붙인다(와이어 · 기록 탭 일정별 묶음에 그대로 들어감)
    winners = [r for r in ranked if r.percent == ranked[0].percent]
    for r in winners:
        db.add(MemberTitle(club_id=club.club_id, title_type_id=t.title_type_id, member_id=r.member_id,
                           period_start=start, period_end=end, session_id=anchor.session_id,
                           award_method=AwardMethod.AUTO,
                           facts_json={"metric": "risePercent", "value": r.percent, "tied": len(winners) > 1,
                                       "sessions": r.sessions, "games": r.games}))
    db.flush()
    rebuild_member_stats(db, club.club_id)
    context = {"month": start.strftime("%Y-%m"), "monthLabel": f"{start.month}월",
               "monthlyMvp": monthly_facts(db, club.club_id, start, end, ranked, min_sessions)}
    article = create_article(db, club, anchor, ArticleType.MONTHLY_MVP, [], context)
    emit(db, club.club_id, "TITLE_UPDATED", {"titleCode": MVP_CODE, "month": context["month"]})
    db.commit()
    return [article.article_id]


def monthly_facts(db: Session, club_id: int, start: date, end: date, ranked: list[MonthRise],
                  min_sessions: int) -> dict:
    """기사용 사실(AI DTO). 점수 자체는 넣지 않고 상승률만."""
    winners = [r for r in ranked if r.percent == ranked[0].percent]
    names = member_names(db, [r.member_id for r in ranked[:RACE_SIZE + len(winners)]])
    history = {r.match_id: r for r in load_history(
        db, club_id, session_ids=list({s.session_id for w in winners for s in w.steps}))}
    team_codes = {t.session_team_id: t.team_code for t in db.scalars(
        select(SessionTeam).where(SessionTeam.session_id.in_({m.session_id for m in history.values()})))}

    def winner(r: MonthRise) -> dict:
        wins = draws = losses = goals = assists = 0
        for st in r.steps:
            rec = history.get(st.match_id)
            if not rec:
                continue
            res = rec.result_of(r.member_id)
            wins, draws, losses = wins + (res == "W"), draws + (res == "D"), losses + (res == "L")
            goals += rec.member_goals(r.member_id)
            assists += rec.member_assists(r.member_id)
        best = sorted((s for s in r.steps if s.change > 0), key=lambda s: -s.change)[:3]
        by_day: dict[int, list[_Step]] = defaultdict(list)
        for s in r.steps:
            by_day[s.session_id].append(s)
        day = max(by_day.values(), key=lambda ss: sum(x.change for x in ss) / ss[0].before)
        day_rec = [history[s.match_id] for s in day if s.match_id in history]
        return {
            "memberId": r.member_id, "name": names.get(r.member_id), "risePercent": r.percent,
            "sessions": r.sessions, "games": r.games, "wins": wins, "draws": draws, "losses": losses,
            "goals": goals, "assists": assists,
            "bestMatches": [_match_fact(history.get(s.match_id), r.member_id, s, team_codes) for s in best],
            "bestDay": {
                "sessionDate": day[0].session_date.isoformat(), "games": len(day),
                "risePercent": round(sum(x.change for x in day) / day[0].before * 100, 2),
                "wins": sum(1 for rec in day_rec if rec.result_of(r.member_id) == "W"),
                "goals": sum(rec.member_goals(r.member_id) for rec in day_rec),
                "assists": sum(rec.member_assists(r.member_id) for rec in day_rec),
            },
        }

    return {
        "winners": [winner(r) for r in winners],
        "runnersUp": [{"rank": i + 1, "memberId": r.member_id, "name": names.get(r.member_id),
                       "risePercent": r.percent, "sessions": r.sessions, "games": r.games}
                      for i, r in enumerate(ranked[:RACE_SIZE]) if r not in winners],
        "candidateCount": len(ranked),
        "rule": f"이번 달 일정 {min_sessions}회 이상 출전한 선수 중 실력 점수 상승률(%) 1위",
    }


def _match_fact(rec, member_id: int, step: _Step, team_codes: dict[int, str]) -> dict:
    fact = {"sessionDate": step.session_date.isoformat(), "gameNo": step.game_no,
            "risePercent": round(step.change / step.before * 100, 2) if step.before else 0.0}
    if rec is None:
        return fact
    team = rec.members.get(member_id)
    mine, theirs = (rec.score_a, rec.score_b) if team == rec.team_a_id else (rec.score_b, rec.score_a)
    fact.update({"result": rec.result_of(member_id), "teamCode": team_codes.get(team),
                 "opponentTeamCode": team_codes.get(rec.opponent_of(team)) if team else None,
                 "score": f"{mine} : {theirs}", "goals": rec.member_goals(member_id),
                 "assists": rec.member_assists(member_id)})
    return fact
