"""이달의 MVP: 월 마감 때 자동 선정.

[2026-11부터: 월간 포인트제]
- 최종 포인트 = 월간 승점 × 실력 점수 배율
  · 월간 승점: 그 달 확정 경기 승 3점 · 무 1점 · 패 0점(원정 경기는 제외)
  · 배율 = 그 달 마지막 경기 후 점수 ÷ 그 달 첫 경기 전 점수(소수 넷째 자리 반올림)
  · 포인트는 소수 둘째 자리까지(반올림). 예: 10승(30점) × 1.01 = 30.3
- 후보 자격: 그 달 출전 일정 수 >= MONTHLY_MVP_MIN_SESSIONS(기본 2) 이고 승점 1점 이상
- 포인트가 같으면: ① 그 달 이전 MVP 수상 횟수가 적은 선수 → ② 그 달 득점 → ③ 그 달 도움
  → ④ 나이가 어린 선수(출생연도. 동점자 중 한 명이라도 비어 있거나 같으면 건너뜀) → ⑤ 공동 수상
- 화면·API·기사에는 포인트 · 승점 · 배율만 내보내고 점수 자체는 내보내지 않는다(Rating은 DB에서만).

[2026-10까지: 실력 점수 상승률] — 아직 마감하지 않은 지난 달에만 쓰는 이전 방식(이미 발표한 MVP는 다시 계산하지 않는다)
- 상승률 = (그 달 마지막 경기 후 점수 - 그 달 첫 경기 전 점수) ÷ 첫 경기 전 점수 × 100
  점수는 PLAYER_RATING_HISTORY(무효 처리 안 된 경기 이력)에서 읽는다.
- 후보 자격: 그 달 출전 일정 수 >= MONTHLY_MVP_MIN_SESSIONS(기본 2) 이고 상승률 > 0

[공통]
- 월 마감: 클럽 현지 날짜로 다음 달이 되고, 그 달 일정이 모두 마감/취소되면
  → MEMBER_TITLE(이달의 MVP) 수여 + MONTHLY_MVP 기사 작성(게시 설정과 상관없이 바로 게시)
- 한 달은 한 번만 마감한다(수여 이력이 있으면 관리자가 취소한 것이라도 다시 만들지 않음).
- 이달의 득점왕 · 도움왕(2026-10-23): 같은 월 마감 때 그 달 확정 경기 골 · 도움 1위(동점 공동, 0개면 없음).
  타이틀 종류마다 따로 '이미 수여했는지' 보므로, 배포 전에 MVP만 발표된 달도 득점왕 · 도움왕은 채워진다.
"""
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date
from decimal import ROUND_HALF_UP, Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.database import emit
from app.core.timeutil import local_today, month_range, prev_month_start
from app.models import (
    AiArticle,
    Club,
    ClubSession,
    MatchGame,
    Member,
    MemberTitle,
    PlayerRatingHistory,
    SessionTeam,
    TitleType,
)
from app.models.enums import (
    ArticleType,
    AwardMethod,
    ReferenceType,
    SessionStatus,
    TitleAutoRule,
    TitlePeriodType,
)
from app.services.common import deleted_member_ids, lock_club, member_names
from app.services.config_service import load_config
from app.services.history import load_history, member_totals
from app.services.stats_service import rebuild_member_stats
from app.wire.article_service import create_article

MVP_CODE = "MONTHLY_MVP"
MVP_NAME = "이달의 MVP"
RACE_SIZE = 3  # 홈 화면 후보 수
POINTS_FROM = date(2026, 11, 1)  # 이 달부터 월간 포인트제(그 전 달은 실력 점수 상승률)
WIN_POINTS, DRAW_POINTS = 3, 1   # 월간 승점: 승 3 · 무 1 · 패 0
# 이달의 득점왕 · 도움왕: (코드, 이름, 규칙, 집계 항목, 표시 순서)
MONTHLY_STAT_TITLES = (
    ("MONTHLY_TOP_SCORER", "이달의 득점왕", TitleAutoRule.TOP_GOALS, "goals", 3),
    ("MONTHLY_TOP_ASSIST", "이달의 도움왕", TitleAutoRule.TOP_ASSISTS, "assists", 4),
)


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
    """후보(자격 충족 + 상승) 상승률 높은 순. 같으면 경기 수 많은 순. 삭제한 선수는 후보 · 수상에서 뺀다."""
    deleted = deleted_member_ids(db, club_id)
    rises = [r for r in month_rises(db, club_id, start, end).values()
             if r.sessions >= min_sessions and r.percent > 0 and r.member_id not in deleted]
    return sorted(rises, key=lambda r: (-r.percent, -r.games, r.member_id))


def uses_points(month_start: date) -> bool:
    """그 달 MVP를 월간 포인트제로 뽑는가(2026-11부터)."""
    return month_start >= POINTS_FROM


def _q(value, places: int) -> float:
    """소수 places자리 반올림(0.5는 올림). 화면에 보이는 값끼리 계산이 맞도록 Decimal로 계산한다."""
    return float(Decimal(str(value)).quantize(Decimal(1).scaleb(-places), rounding=ROUND_HALF_UP))


@dataclass
class MonthPoints:
    """한 선수의 월간 포인트: 승점 × 실력 점수 배율."""
    rise: MonthRise
    wins: int = 0
    draws: int = 0
    losses: int = 0
    goals: int = 0
    assists: int = 0
    mvp_count: int = 0             # 그 달 이전 MVP 수상 횟수(동점 1순위: 적은 선수 우선)
    birth_year: int | None = None  # 동점 4순위: 어린 선수 우선

    @property
    def member_id(self) -> int:
        return self.rise.member_id

    @property
    def sessions(self) -> int:
        return self.rise.sessions

    @property
    def games(self) -> int:
        return self.rise.games

    @property
    def win_points(self) -> int:
        return self.wins * WIN_POINTS + self.draws * DRAW_POINTS

    @property
    def ratio(self) -> float:
        """실력 점수 배율(월말 ÷ 월초, 소수 넷째 자리)."""
        return _q(self.rise.end / self.rise.start, 4) if self.rise.start else 1.0

    @property
    def points(self) -> float:
        """최종 포인트 = 승점 × 배율(소수 둘째 자리)."""
        return _q(Decimal(self.win_points) * Decimal(str(self.ratio)), 2)

    def facts(self) -> dict:
        return {"points": self.points, "winPoints": self.win_points, "ratio": self.ratio,
                "wins": self.wins, "draws": self.draws, "losses": self.losses,
                "sessions": self.sessions, "games": self.games}


def _prior_mvp_counts(db: Session, club_id: int, before: date) -> dict[int, int]:
    """그 달 이전 MVP 수상 횟수(선수 화면의 MVP 수와 같은 기준: 'MVP로 세는' 타이틀, 취소 · 비활성 제외)."""
    return dict(db.execute(
        select(MemberTitle.member_id, func.count())
        .join(TitleType, TitleType.title_type_id == MemberTitle.title_type_id)
        .where(MemberTitle.club_id == club_id, MemberTitle.cancelled_yn.is_(False), TitleType.active_yn.is_(True),
               TitleType.counts_as_mvp_yn.is_(True), MemberTitle.period_start < before)
        .group_by(MemberTitle.member_id)).all())


def month_points(db: Session, club_id: int, start: date, end: date) -> dict[int, MonthPoints]:
    """기간 안 확정 경기(내부 경기만)의 선수별 승 · 무 · 패 · 골 · 도움 + 실력 점수 변화."""
    rises = month_rises(db, club_id, start, end)
    session_ids = list({st.session_id for r in rises.values() for st in r.steps})
    history = {rec.match_id: rec for rec in load_history(db, club_id, session_ids=session_ids)} if session_ids else {}
    mvp_counts = _prior_mvp_counts(db, club_id, start)
    births = dict(db.execute(select(Member.member_id, Member.birth_year).where(Member.club_id == club_id)).all())
    out: dict[int, MonthPoints] = {}
    for mid, r in rises.items():
        p = MonthPoints(r, mvp_count=mvp_counts.get(mid, 0), birth_year=births.get(mid))
        for st in r.steps:
            rec = history.get(st.match_id)
            if rec is None:
                continue
            res = rec.result_of(mid)
            p.wins, p.draws, p.losses = p.wins + (res == "W"), p.draws + (res == "D"), p.losses + (res == "L")
            p.goals += rec.member_goals(mid)
            p.assists += rec.member_assists(mid)
        out[mid] = p
    return out


def _tie_key(p: MonthPoints) -> tuple:
    """포인트 → MVP 수상 횟수 적은 순 → 그 달 득점 → 그 달 도움."""
    return (-p.points, p.mvp_count, -p.goals, -p.assists)


def rank_points(cands: list[MonthPoints]) -> list[tuple[int, MonthPoints]]:
    """동점 규칙까지 적용한 순위(같은 순위 = 끝까지 같음 → 1위면 공동 수상)."""
    ordered = sorted(cands, key=lambda p: (*_tie_key(p), p.member_id))
    out: list[tuple[int, MonthPoints]] = []
    i = 0
    while i < len(ordered):
        j = i
        while j < len(ordered) and _tie_key(ordered[j]) == _tie_key(ordered[i]):
            j += 1
        group = ordered[i:j]
        if len(group) > 1 and all(p.birth_year for p in group):
            # 나이가 어린 선수 우선(출생연도가 늦은 순). 한 명이라도 출생연도가 없으면 나이로 가리지 않는다
            group.sort(key=lambda p: (-p.birth_year, p.member_id))
            k = 0
            while k < len(group):
                m = k
                while m < len(group) and group[m].birth_year == group[k].birth_year:
                    m += 1
                out += [(i + k + 1, p) for p in group[k:m]]
                k = m
        else:
            out += [(i + 1, p) for p in group]
        i = j
    return out


def points_ranking(db: Session, club_id: int, start: date, end: date,
                   min_sessions: int) -> list[tuple[int, MonthPoints]]:
    """포인트제 후보(자격 충족 + 승점 1점 이상) 순위. 삭제한 선수는 후보 · 수상에서 뺀다."""
    deleted = deleted_member_ids(db, club_id)
    cands = [p for p in month_points(db, club_id, start, end).values()
             if p.sessions >= min_sessions and p.win_points > 0 and p.member_id not in deleted]
    return rank_points(cands)


TIEBREAK_LABEL = {"mvpCount": "MVP 수상 횟수가 적은 선수", "goals": "그 달 득점이 많은 선수",
                  "assists": "그 달 도움이 많은 선수", "age": "나이가 어린 선수"}


def tiebreak_info(ranked: list[tuple[int, MonthPoints]]) -> dict | None:
    """1위 포인트가 같은 선수가 둘 이상일 때: 몇 명이 같았고 무엇으로 갈렸는지(끝까지 같으면 공동 수상)."""
    if not ranked:
        return None
    winners = [p for r, p in ranked if r == 1]
    same = [p for _, p in ranked if p.points == winners[0].points]
    if len(same) < 2:
        return None
    pool, decided = same, None
    for key, best in (("mvpCount", lambda ps: min(p.mvp_count for p in ps)), ("goals", lambda ps: max(p.goals for p in ps)),
                      ("assists", lambda ps: max(p.assists for p in ps))):
        attr = {"mvpCount": "mvp_count"}.get(key, key)
        target = best(pool)
        nxt = [p for p in pool if getattr(p, attr) == target]
        if len(nxt) < len(pool):
            pool, decided = nxt, key
    if len(pool) > len(winners):
        decided = "age"
    return {"tiedCount": len(same), "decidedBy": decided, "decidedByLabel": TIEBREAK_LABEL.get(decided),
            "joint": len(winners) > 1}


def _point_candidates(db: Session, ranked: list[tuple[int, MonthPoints]]) -> list[dict]:
    names = member_names(db, [p.member_id for _, p in ranked])
    return [{"rank": rank, "memberId": p.member_id, "name": names.get(p.member_id), **p.facts()} for rank, p in ranked]


def _candidates(db: Session, ranked: list[MonthRise]) -> list[dict]:
    names = member_names(db, [r.member_id for r in ranked])
    out, rank = [], 0
    for i, r in enumerate(ranked):
        if i == 0 or r.percent != ranked[i - 1].percent:
            rank = i + 1
        out.append({"rank": rank, "memberId": r.member_id, "name": names.get(r.member_id),
                    "risePercent": r.percent, "sessions": r.sessions, "games": r.games})
    return out


def _monthly_type(db: Session, club_id: int, code: str, name: str, rule: str, order: int, *,
                  counts_as_mvp: bool = False, create: bool = False) -> TitleType | None:
    """월간 타이틀 정의. 없으면(기존 클럽 · 샘플 데이터 복원 후) 만든다. 관리자가 비활성화했으면 None."""
    t = db.scalar(select(TitleType).where(TitleType.club_id == club_id, TitleType.title_code == code))
    if t is None and create:
        t = TitleType(club_id=club_id, title_code=code, title_name=name, period_type=TitlePeriodType.MONTHLY,
                      award_method=AwardMethod.AUTO, auto_rule=rule, counts_as_mvp_yn=counts_as_mvp,
                      display_order=order)
        db.add(t)
        db.flush()
    return t if t is not None and t.active_yn else None


def _mvp_type(db: Session, club_id: int, create: bool = False) -> TitleType | None:
    """'이달의 MVP' 타이틀 정의."""
    return _monthly_type(db, club_id, MVP_CODE, MVP_NAME, TitleAutoRule.MONTHLY_RATING_RISE, 2,
                         counts_as_mvp=True, create=create)


def mvp_race(db: Session, club: Club, today: date | None = None) -> dict:
    """홈 화면: 이번 달 후보 1~3위 + 지난달 MVP. basis = points(포인트 · 승점 · 배율) / rise(상승률만)."""
    today = today or local_today(club.timezone)
    start, end = month_range(today)
    min_sessions = int(load_config(db, club.club_id)["MONTHLY_MVP_MIN_SESSIONS"])
    if uses_points(start):
        basis = "points"
        candidates = _point_candidates(db, points_ranking(db, club.club_id, start, end, min_sessions)[:RACE_SIZE])
    else:
        basis = "rise"
        candidates = _candidates(db, ranking(db, club.club_id, start, end, min_sessions)[:RACE_SIZE])
    return {"month": start.strftime("%Y-%m"), "minSessions": min_sessions, "basis": basis, "candidates": candidates,
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
            "winners": [{"memberId": x.member_id, "name": names.get(x.member_id), **_award_value(x.facts_json)}
                        for x in titles]}


def _award_value(facts: dict | None) -> dict:
    """수상 값: metric = mvpPoints(포인트제) / risePercent(이전 방식). risePercent는 이전 화면 호환용."""
    facts = facts or {}
    metric = facts.get("metric") or "risePercent"
    return {"metric": metric, "value": facts.get("value"),
            "risePercent": facts.get("value") if metric == "risePercent" else None}


# ------------------------------------------------------------------ 월 마감
def close_due_month(db: Session, club: Club, today: date | None = None) -> list[int]:
    """지난달 마감이 가능하면 마감한다. 반환: 새로 만든 기사 ID(호출 측이 생성 실행)."""
    today = today or local_today(club.timezone)
    return close_month(db, club, prev_month_start(today))


def close_month(db: Session, club: Club, month_start: date) -> list[int]:
    start, end = month_range(month_start)
    lock_club(db, club.club_id)
    mvp_t = _mvp_type(db, club.club_id, create=True)
    stat_ts = [(_monthly_type(db, club.club_id, code, name, rule, order, create=True), metric)
               for code, name, rule, metric, order in MONTHLY_STAT_TITLES]

    def todo(t: TitleType | None) -> bool:  # 이 달에 아직 수여한 적 없는 타이틀만(취소된 수여도 '했음')
        return t is not None and db.scalar(select(MemberTitle.member_title_id).where(
            MemberTitle.title_type_id == t.title_type_id, MemberTitle.period_start == start).limit(1)) is None

    stat_ts = [(t, m) for t, m in stat_ts if todo(t)]
    mvp_t = mvp_t if todo(mvp_t) else None
    sessions = list(db.scalars(select(ClubSession).where(
        ClubSession.club_id == club.club_id, ClubSession.session_date.between(start, end),
        ClubSession.away_yn.is_(False),  # 원정 경기는 이달의 MVP · 득점왕 · 도움왕과 무관
        ClubSession.status != SessionStatus.CANCELLED).order_by(ClubSession.session_date, ClubSession.session_id)))
    # 할 일 없음 / 일정 없음 / 아직 안 끝난 일정이 있음 → 다음에 다시 확인
    if not (mvp_t or stat_ts) or not sessions or any(s.status != SessionStatus.CLOSED for s in sessions):
        db.commit()  # 타이틀 정의를 새로 만들었으면 저장
        return []
    anchor = sessions[-1]  # 타이틀 · 기사는 그 달 마지막 일정에 붙인다(와이어 · 기록 탭 일정별 묶음에 그대로 들어감)

    # 이달의 득점왕 · 도움왕: 그 달 확정 경기 골 · 도움 1위(동점 공동)
    totals = member_totals(load_history(db, club.club_id, session_ids=[x.session_id for x in sessions]))
    deleted = deleted_member_ids(db, club.club_id)  # 삭제한 선수에게는 새로 수여하지 않음
    totals = {mid: v for mid, v in totals.items() if mid not in deleted}
    awarded = 0
    for t, metric in stat_ts:
        best = max((getattr(v, metric) for v in totals.values()), default=0)
        top = sorted(mid for mid, v in totals.items() if best > 0 and getattr(v, metric) == best)
        for mid in top:
            db.add(MemberTitle(club_id=club.club_id, title_type_id=t.title_type_id, member_id=mid, period_start=start,
                               period_end=end, session_id=anchor.session_id, award_method=AwardMethod.AUTO,
                               facts_json={"metric": metric, "value": best, "tied": len(top) > 1}))
        awarded += len(top)

    # 이달의 MVP: 2026-11부터 월간 포인트 1위(동점 규칙 적용), 그 전 달은 실력 점수 상승률 1위
    min_sessions = int(load_config(db, club.club_id)["MONTHLY_MVP_MIN_SESSIONS"])
    by_points = uses_points(start)
    ranked_points = points_ranking(db, club.club_id, start, end, min_sessions) if mvp_t and by_points else []
    ranked = ranking(db, club.club_id, start, end, min_sessions) if mvp_t and not by_points else []
    if by_points:
        winners = [p for rank, p in ranked_points if rank == 1]
        award_facts = {p.member_id: {"metric": "mvpPoints", "value": p.points, "tied": len(winners) > 1, **p.facts(),
                                     "goals": p.goals, "assists": p.assists} for p in winners}
    else:
        winners = [r for r in ranked if r.percent == ranked[0].percent] if ranked else []
        award_facts = {r.member_id: {"metric": "risePercent", "value": r.percent, "tied": len(winners) > 1,
                                     "sessions": r.sessions, "games": r.games} for r in winners}
    for mid, facts_json in award_facts.items():
        db.add(MemberTitle(club_id=club.club_id, title_type_id=mvp_t.title_type_id, member_id=mid,
                           period_start=start, period_end=end, session_id=anchor.session_id,
                           award_method=AwardMethod.AUTO, facts_json=facts_json))
    if not awarded and not winners:
        db.commit()
        return []
    db.flush()
    rebuild_member_stats(db, club.club_id)
    article_ids: list[int] = []
    if winners:  # 발표 기사는 MVP가 나온 달만(득점왕 · 도움왕은 기사 마지막 문단에)
        facts = (monthly_points_facts(db, club.club_id, ranked_points, min_sessions) if by_points
                 else monthly_facts(db, club.club_id, start, end, ranked, min_sessions))
        facts["monthlyTitles"] = monthly_titles(db, club.club_id, start)
        context = {"month": start.strftime("%Y-%m"), "monthLabel": f"{start.month}월", "monthlyMvp": facts}
        article_ids.append(create_article(db, club, anchor, ArticleType.MONTHLY_MVP, [], context).article_id)
    emit(db, club.club_id, "TITLE_UPDATED", {"month": start.strftime("%Y-%m")})
    db.commit()
    return article_ids


def monthly_titles(db: Session, club_id: int, month_start: date) -> list[dict]:
    """그 달 이달의 득점왕 · 도움왕(기사용): [{titleName, metric, value, names[]}]"""
    rows = db.execute(
        select(MemberTitle, TitleType).join(TitleType, TitleType.title_type_id == MemberTitle.title_type_id)
        .where(MemberTitle.club_id == club_id, MemberTitle.period_start == month_start,
               MemberTitle.cancelled_yn.is_(False), TitleType.active_yn.is_(True),
               TitleType.title_code.in_([c for c, *_ in MONTHLY_STAT_TITLES]))
        .order_by(TitleType.display_order, MemberTitle.member_id)).all()
    names = member_names(db, [mt.member_id for mt, _ in rows])
    out: dict[str, dict] = {}
    for mt, t in rows:
        item = out.setdefault(t.title_code, {"titleName": t.title_name, "metric": (mt.facts_json or {}).get("metric"),
                                             "value": (mt.facts_json or {}).get("value"), "names": []})
        item["names"].append(names.get(mt.member_id))
    return list(out.values())


def points_rule(min_sessions: int) -> str:
    return (f"월간 승점(승 {WIN_POINTS}점 · 무 {DRAW_POINTS}점, 원정 경기 제외)에 실력 점수 배율(월말 ÷ 월초)을 곱한 "
            f"포인트 1위(이번 달 일정 {min_sessions}회 이상 출전)")


def monthly_points_facts(db: Session, club_id: int, ranked: list[tuple[int, MonthPoints]], min_sessions: int) -> dict:
    """기사용 사실(AI DTO, 포인트제). 점수 자체는 넣지 않고 포인트 · 승점 · 배율만."""
    winners = [p for rank, p in ranked if rank == 1]
    names = member_names(db, [p.member_id for _, p in ranked[:RACE_SIZE + len(winners)]])
    history = {rec.match_id: rec for rec in load_history(
        db, club_id, session_ids=list({s.session_id for w in winners for s in w.rise.steps}))}

    def winner(p: MonthPoints) -> dict:
        by_day: dict[int, dict] = {}
        for st in p.rise.steps:
            rec = history.get(st.match_id)
            if rec is None:
                continue
            d = by_day.setdefault(st.session_id, {"sessionDate": st.session_date.isoformat(), "games": 0, "wins": 0,
                                                  "draws": 0, "losses": 0, "goals": 0, "assists": 0})
            res = rec.result_of(p.member_id)
            d["games"] += 1
            d["wins"], d["draws"], d["losses"] = d["wins"] + (res == "W"), d["draws"] + (res == "D"), d["losses"] + (res == "L")
            d["goals"] += rec.member_goals(p.member_id)
            d["assists"] += rec.member_assists(p.member_id)
        for d in by_day.values():
            d["winPoints"] = d["wins"] * WIN_POINTS + d["draws"] * DRAW_POINTS
        best = max(by_day.values(), key=lambda d: (d["winPoints"], d["goals"] + d["assists"], d["sessionDate"]),
                   default=None)
        return {"memberId": p.member_id, "name": names.get(p.member_id), **p.facts(),
                "goals": p.goals, "assists": p.assists, "mvpCount": p.mvp_count, "bestDay": best}

    return {
        "basis": "points",
        "winners": [winner(p) for p in winners],
        "runnersUp": [{"rank": rank, "memberId": p.member_id, "name": names.get(p.member_id), **p.facts()}
                      for rank, p in ranked[:RACE_SIZE + len(winners)] if rank != 1][:RACE_SIZE - 1],
        "candidateCount": len(ranked),
        "tiebreak": tiebreak_info(ranked),
        "rule": points_rule(min_sessions),
    }


def monthly_facts(db: Session, club_id: int, start: date, end: date, ranked: list[MonthRise],
                  min_sessions: int) -> dict:
    """기사용 사실(AI DTO, 2026-10까지의 상승률 방식). 점수 자체는 넣지 않고 상승률만."""
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
