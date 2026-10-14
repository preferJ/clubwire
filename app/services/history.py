"""확정 경기 원본 데이터를 시간순으로 읽어오는 공용 로더.

Stats / Pair / Insight가 모두 같은 원본(MATCH_GAME, MATCH_MEMBER, MATCH_EVENT)에서 계산되도록 한다.
"""
from dataclasses import dataclass, field
from datetime import date

from sqlalchemy import select, tuple_
from sqlalchemy.orm import Session

from app.models import ClubSession, MatchEvent, MatchGame, MatchMember
from app.models.enums import EventType, GameStatus, SessionStatus


@dataclass
class GoalRecord:
    event_id: int
    team_id: int
    scorer_member_id: int | None
    assist_member_id: int | None
    own_goal: bool
    guest_goal: bool
    elapsed_sec: int | None
    remaining_sec: int | None


@dataclass
class MatchRecord:
    match_id: int
    session_id: int
    session_date: date
    game_no: int
    team_a_id: int
    team_b_id: int
    score_a: int
    score_b: int
    win_team_id: int | None
    expected_a: float | None
    duration_sec: int
    members: dict[int, int] = field(default_factory=dict)  # member_id -> session_team_id
    goals: list[GoalRecord] = field(default_factory=list)

    def result_of(self, member_id: int) -> str | None:
        team = self.members.get(member_id)
        if team is None:
            return None
        if self.win_team_id is None:
            return "D"
        return "W" if self.win_team_id == team else "L"

    def opponent_of(self, team_id: int) -> int:
        return self.team_b_id if team_id == self.team_a_id else self.team_a_id

    def member_goals(self, member_id: int) -> int:
        return sum(1 for g in self.goals if g.scorer_member_id == member_id and not g.own_goal)

    def member_assists(self, member_id: int) -> int:
        return sum(1 for g in self.goals if g.assist_member_id == member_id)


def load_history(
    db: Session,
    club_id: int,
    *,
    before_session: ClubSession | None = None,
    upto_session: ClubSession | None = None,
    session_ids: list[int] | None = None,
) -> list[MatchRecord]:
    stmt = (
        select(MatchGame, ClubSession.session_date)
        .join(ClubSession, ClubSession.session_id == MatchGame.session_id)
        .where(
            ClubSession.club_id == club_id,
            ClubSession.status != SessionStatus.CANCELLED,
            MatchGame.game_status == GameStatus.FINISHED,
            MatchGame.finalized_at.is_not(None),
        )
    )
    if before_session is not None:
        stmt = stmt.where(
            tuple_(ClubSession.session_date, ClubSession.session_id)
            < tuple_(before_session.session_date, before_session.session_id)
        )
    if upto_session is not None:
        stmt = stmt.where(
            tuple_(ClubSession.session_date, ClubSession.session_id)
            <= tuple_(upto_session.session_date, upto_session.session_id)
        )
    if session_ids is not None:
        stmt = stmt.where(ClubSession.session_id.in_(session_ids))
    stmt = stmt.order_by(ClubSession.session_date, ClubSession.session_id, MatchGame.game_no)

    records: dict[int, MatchRecord] = {}
    for m, sdate in db.execute(stmt).all():
        records[m.match_id] = MatchRecord(
            match_id=m.match_id, session_id=m.session_id, session_date=sdate, game_no=m.game_no,
            team_a_id=m.team_a_id, team_b_id=m.team_b_id, score_a=m.score_a, score_b=m.score_b,
            win_team_id=m.win_team_id, expected_a=m.expected_a, duration_sec=m.game_duration_sec,
        )
    if not records:
        return []
    ids = list(records)
    for mm in db.scalars(select(MatchMember).where(MatchMember.match_id.in_(ids))):
        records[mm.match_id].members[mm.member_id] = mm.session_team_id
    goal_rows = db.scalars(
        select(MatchEvent)
        .where(MatchEvent.match_id.in_(ids), MatchEvent.event_type == EventType.GOAL, MatchEvent.cancelled_yn.is_(False))
        .order_by(MatchEvent.match_id, MatchEvent.elapsed_sec, MatchEvent.event_id)
    )
    for e in goal_rows:
        records[e.match_id].goals.append(
            GoalRecord(e.event_id, e.team_id, e.scorer_member_id, e.assist_member_id, e.own_goal_yn,
                       e.guest_goal_yn, e.elapsed_sec, e.remaining_sec)
        )
    return list(records.values())


@dataclass
class MemberTotals:
    games: int = 0
    wins: int = 0
    draws: int = 0
    losses: int = 0
    goals: int = 0
    assists: int = 0
    own_goals: int = 0
    sessions: set = field(default_factory=set)
    last_played_date: date | None = None


def member_totals(records: list[MatchRecord]) -> dict[int, MemberTotals]:
    totals: dict[int, MemberTotals] = {}
    for r in records:
        for mid in r.members:
            t = totals.setdefault(mid, MemberTotals())
            t.games += 1
            res = r.result_of(mid)
            if res == "W":
                t.wins += 1
            elif res == "D":
                t.draws += 1
            else:
                t.losses += 1
            t.sessions.add(r.session_id)
            if t.last_played_date is None or r.session_date > t.last_played_date:
                t.last_played_date = r.session_date
        for g in r.goals:
            if g.scorer_member_id is not None:
                t = totals.setdefault(g.scorer_member_id, MemberTotals())
                if g.own_goal:
                    t.own_goals += 1
                else:
                    t.goals += 1
            if g.assist_member_id is not None:
                totals.setdefault(g.assist_member_id, MemberTotals()).assists += 1
    return totals


def win_streak(records: list[MatchRecord], member_id: int) -> int:
    """가장 최근부터 연속 승리 수(무승부/패배에서 끊김)."""
    streak = 0
    for r in reversed(records):
        res = r.result_of(member_id)
        if res is None:
            continue
        if res == "W":
            streak += 1
        else:
            break
    return streak


def scoring_session_streak(records: list[MatchRecord], member_id: int) -> int:
    """가장 최근 출전 일정부터 연속으로 골을 넣은 일정 수."""
    by_session: dict[int, int] = {}
    order: list[int] = []
    for r in records:
        if member_id not in r.members:
            continue
        if r.session_id not in by_session:
            by_session[r.session_id] = 0
            order.append(r.session_id)
        by_session[r.session_id] += r.member_goals(member_id)
    streak = 0
    for sid in reversed(order):
        if by_session[sid] > 0:
            streak += 1
        else:
            break
    return streak


def last_played_date(records: list[MatchRecord], member_id: int) -> date | None:
    for r in reversed(records):
        if member_id in r.members:
            return r.session_date
    return None
