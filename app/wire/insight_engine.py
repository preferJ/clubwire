"""Insight Generator.

AI는 사실을 판단하지 않는다. 복귀 일수, 연승, 이변, 결승골 여부 등은 전부 여기서 계산해
구조화된 사실(FACTS_JSON)로 저장한다. 사용자에게 노출하지 않는 내부 수치(Rating, 기대승률)는
FACTS에 넣지 않는다.

- PRE  : [일정확정] 시점. 해당 일정 이전의 확정 경기만 사용.
- POST : [일정마감] 시점. 해당 일정까지의 확정 경기 사용.
"""
from dataclasses import dataclass, field
from datetime import date
from itertools import combinations

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.models import (
    ClubSession,
    Insight,
    InsightConfigParam,
    InsightMember,
    InsightTypeConfig,
    Member,
    MemberTitle,
    SessionTeam,
    SessionTeamMember,
    TitleType,
)
from app.models.enums import InsightPhase
from app.services.common import session_teams
from app.services.history import (
    MatchRecord,
    last_played_date,
    load_history,
    member_totals,
    scoring_session_streak,
    win_streak,
)
from app.services.stats_service import aggregate_pairs
from app.strategies.importance import importance_strategy
from app.strategies.team_generation import spread_percent
from app.wire.insight_types import ensure_insight_types


@dataclass
class _Ctx:
    db: Session
    club_id: int
    session: ClubSession
    phase: str
    types: dict[str, InsightTypeConfig]
    params: dict[str, dict[str, str]]
    names: dict[int, str]
    created: list[Insight] = field(default_factory=list)

    def enabled(self, t: str) -> bool:
        c = self.types.get(t)
        if not c or not c.enabled_yn:
            return False
        return c.pre_match_yn if self.phase == InsightPhase.PRE else c.post_match_yn

    def p(self, t: str, key: str, default: float) -> float:
        try:
            return float(self.params.get(t, {}).get(key, default))
        except ValueError:
            return default

    def ps(self, t: str, key: str, default: str) -> str:
        return self.params.get(t, {}).get(key, default)

    def imp_linear(self, t: str, signal: float, lo: float, hi: float) -> int:
        c = self.types[t]
        return importance_strategy.linear(signal, lo, hi, c.base_importance, c.max_importance, c.min_importance)

    def imp_step(self, t: str, steps: float, per_step: float) -> int:
        c = self.types[t]
        return int(max(c.min_importance, min(c.max_importance, c.base_importance + steps * per_step)))

    def add(self, t: str, importance: int, facts: dict, *, members: list[tuple[int, str]] | None = None,
            match_id: int | None = None) -> Insight:
        c = self.types[t]
        members = members or []
        ins = Insight(
            club_id=self.club_id, session_id=self.session.session_id, match_id=match_id,
            member_id=members[0][0] if members else None, insight_type=t, category=c.category, phase=self.phase,
            importance=int(importance), facts_json=facts, rule_version=c.rule_version, active_yn=True,
        )
        self.db.add(ins)
        self.db.flush()
        seen = set()
        for mid, role in members:
            if mid in seen:
                continue
            seen.add(mid)
            self.db.add(InsightMember(insight_id=ins.insight_id, member_id=mid, role=role))
        self.created.append(ins)
        return ins

    def person(self, mid: int) -> dict:
        return {"memberId": mid, "name": self.names.get(mid)}


def _context(db: Session, club_id: int, session: ClubSession, phase: str) -> _Ctx:
    ensure_insight_types(db)
    db.flush()
    types = {t.insight_type: t for t in db.scalars(select(InsightTypeConfig))}
    params: dict[str, dict[str, str]] = {}
    for p in db.scalars(select(InsightConfigParam)):
        params.setdefault(p.insight_type, {})[p.param_key] = p.param_value
    names = {m.member_id: m.name for m in db.scalars(select(Member).where(Member.club_id == club_id))}
    return _Ctx(db, club_id, session, phase, types, params, names)


def _deactivate(db: Session, session_id: int, phase: str) -> None:
    db.execute(update(Insight).where(Insight.session_id == session_id, Insight.phase == phase,
                                     Insight.active_yn.is_(True)).values(active_yn=False))


def _milestones(ctx: _Ctx, t: str) -> list[int]:
    raw = ctx.ps(t, "milestones", "10,30,50,100")
    return sorted(int(x) for x in raw.split(",") if x.strip().isdigit())


METRIC_LABEL = {"games": "출전 경기", "goals": "골", "assists": "도움"}


# ====================================================================== PRE
def generate_pre_insights(db: Session, club_id: int, session: ClubSession) -> list[Insight]:
    """[일정확정] 시 호출(호출 측 트랜잭션). 같은 일정의 기존 PRE Insight는 비활성화 후 재생성."""
    _deactivate(db, session.session_id, InsightPhase.PRE)
    ctx = _context(db, club_id, session, InsightPhase.PRE)
    teams = {t.session_team_id: t for t in session_teams(db, session.session_id)}
    roster = list(db.scalars(select(SessionTeamMember).where(SessionTeamMember.session_id == session.session_id,
                                                             SessionTeamMember.active_yn.is_(True))))
    team_of = {stm.member_id: stm.session_team_id for stm in roster}
    players = sorted(team_of)
    history = load_history(db, club_id, before_session=session)
    totals = member_totals(history)

    def team_code(mid: int) -> str | None:
        t = teams.get(team_of.get(mid))
        return t.team_code if t else None

    for mid in players:
        tot = totals.get(mid)
        # RETURN_PLAYER
        t = "RETURN_PLAYER"
        last = last_played_date(history, mid)
        if ctx.enabled(t) and last:
            days = (session.session_date - last).days
            th = ctx.p(t, "threshold_days", 30)
            if days >= th:
                ctx.add(t, ctx.imp_linear(t, days, th, ctx.p(t, "max_days", 120)),
                        {"member": ctx.person(mid), "daysSinceLastAppearance": days,
                         "lastAppearanceDate": last.isoformat(), "teamCode": team_code(mid)},
                        members=[(mid, "SUBJECT")])
        # FIRST_APPEARANCE
        t = "FIRST_APPEARANCE"
        if ctx.enabled(t) and (tot is None or tot.games == 0):
            ctx.add(t, ctx.types[t].base_importance,
                    {"member": ctx.person(mid), "firstAppearance": True, "teamCode": team_code(mid)},
                    members=[(mid, "SUBJECT")])
        # WIN_STREAK
        t = "WIN_STREAK"
        if ctx.enabled(t):
            streak = win_streak(history, mid)
            mn = ctx.p(t, "minimum_streak", 3)
            if streak >= mn:
                ctx.add(t, ctx.imp_step(t, streak - mn, ctx.p(t, "importance_per_extra_win", 8)),
                        {"member": ctx.person(mid), "streak": streak, "streakUnit": "경기", "teamCode": team_code(mid)},
                        members=[(mid, "SUBJECT")])
        # SCORING_STREAK
        t = "SCORING_STREAK"
        if ctx.enabled(t):
            streak = scoring_session_streak(history, mid)
            mn = ctx.p(t, "minimum_streak", 3)
            if streak >= mn:
                ctx.add(t, ctx.imp_step(t, streak - mn, ctx.p(t, "importance_per_extra", 8)),
                        {"member": ctx.person(mid), "streak": streak, "streakUnit": "일정", "teamCode": team_code(mid)},
                        members=[(mid, "SUBJECT")])
        # MILESTONE_EXPECTED
        t = "MILESTONE_EXPECTED"
        if ctx.enabled(t) and tot:
            ms = _milestones(ctx, t)
            for metric, gap_key in (("games", "games_gap"), ("goals", "goals_gap"), ("assists", "assists_gap")):
                cur = getattr(tot, metric)
                nxt = next((m for m in ms if m > cur), None)
                if nxt is not None and nxt - cur <= ctx.p(t, gap_key, 2):
                    ctx.add(t, ctx.imp_linear(t, nxt, ms[0], ms[-1]),
                            {"member": ctx.person(mid), "metric": metric, "metricLabel": METRIC_LABEL[metric],
                             "current": cur, "milestone": nxt, "remaining": nxt - cur, "teamCode": team_code(mid)},
                            members=[(mid, "SUBJECT")])

    # RARE_PAIR (같은 팀이 된 조합 중)
    t = "RARE_PAIR"
    if ctx.enabled(t):
        pairs = aggregate_pairs(history)  # 이 일정 '이전' 기록만으로 계산
        candidates = []
        by_team: dict[int, list[int]] = {}
        for mid, tid in team_of.items():
            by_team.setdefault(tid, []).append(mid)
        for tid, mids in by_team.items():
            for a, b in combinations(sorted(mids), 2):
                p = pairs.get((a, b))
                if not p or p["co"] < ctx.p(t, "min_co_attendance", 5):
                    continue
                ratio = p["same"] / p["co"]
                since = p["since"]
                if ratio <= ctx.p(t, "max_same_team_ratio", 0.2) and since >= ctx.p(t, "min_sessions_since_same_team", 4):
                    imp = ctx.imp_linear(t, since, ctx.p(t, "min_sessions_since_same_team", 4),
                                         ctx.p(t, "max_sessions_signal", 20))
                    candidates.append((imp, a, b, p, teams[tid].team_code))
        for imp, a, b, p, code in sorted(candidates, key=lambda x: -x[0])[:5]:
            ctx.add(t, imp, {"members": [ctx.person(a), ctx.person(b)], "teamCode": code,
                             "coAttendanceCount": p["co"], "sameTeamCount": p["same"],
                             "sessionsSinceLastSameTeam": p["since"],
                             "lastSameTeamDate": p["last_same"].isoformat() if p["last_same"] else None,
                             "neverSameTeam": p["same"] == 0},
                    members=[(a, "SUBJECT"), (b, "PARTNER")])

    # CLOSE_MATCH_EXPECTED (팀 간 전력 균형. 숫자는 넘기지 않음)
    t = "CLOSE_MATCH_EXPECTED"
    if ctx.enabled(t):
        strengths = [x.team_strength_snapshot for x in teams.values() if x.team_strength_snapshot is not None]
        games = [totals[mid].games if mid in totals else 0 for mid in players]
        avg_games = sum(games) / len(games) if games else 0
        max_spread = ctx.p(t, "max_spread_percent", 1.0)
        if len(strengths) >= 2 and avg_games >= ctx.p(t, "min_avg_match_count", 3):
            sp = spread_percent(strengths)
            if sp <= max_spread:
                ctx.add(t, ctx.imp_linear(t, max_spread - sp, 0, max_spread),
                        {"teamCodes": [x.team_code for x in teams.values()], "balanced": True})
    db.flush()
    return ctx.created


# ====================================================================== POST
def _decisive_goal(r: MatchRecord):
    if r.win_team_id is None:
        return None
    loser_score = r.score_b if r.win_team_id == r.team_a_id else r.score_a
    n = 0
    for g in r.goals:
        if g.team_id == r.win_team_id:
            n += 1
            if n == loser_score + 1:
                return g
    return None


def _max_deficit(r: MatchRecord) -> int:
    if r.win_team_id is None:
        return 0
    mine = theirs = worst = 0
    for g in r.goals:
        if g.team_id == r.win_team_id:
            mine += 1
        else:
            theirs += 1
        worst = max(worst, theirs - mine)
    return worst


def generate_post_insights(db: Session, club_id: int, session: ClubSession) -> list[Insight]:
    """[일정마감] 시 호출(호출 측 트랜잭션)."""
    _deactivate(db, session.session_id, InsightPhase.POST)
    ctx = _context(db, club_id, session, InsightPhase.POST)
    teams = {t.session_team_id: t for t in db.scalars(select(SessionTeam).where(SessionTeam.session_id == session.session_id))}
    upto = load_history(db, club_id, upto_session=session)
    before = [r for r in upto if r.session_id != session.session_id
              and (r.session_date, r.session_id) < (session.session_date, session.session_id)]
    today = [r for r in upto if r.session_id == session.session_id]
    if not today:
        return []

    def code(tid: int | None) -> str | None:
        return teams[tid].team_code if tid in teams else None

    def score_text(r: MatchRecord) -> dict:
        return {"gameNo": r.game_no, "teamA": code(r.team_a_id), "teamB": code(r.team_b_id),
                "scoreA": r.score_a, "scoreB": r.score_b}

    for r in today:
        # LATE_WINNER
        t = "LATE_WINNER"
        g = _decisive_goal(r)
        if ctx.enabled(t) and g and g.scorer_member_id and not g.own_goal and g.remaining_sec is not None:
            mx = ctx.p(t, "max_remaining_sec", 60)
            rem = g.remaining_sec
            if rem <= mx:
                facts = {"member": ctx.person(g.scorer_member_id), "remainingSec": max(rem, 0),
                         "inStoppageTime": rem < 0, "winnerTeam": code(r.win_team_id), **score_text(r)}
                if g.assist_member_id:
                    facts["assist"] = ctx.person(g.assist_member_id)
                ctx.add(t, ctx.imp_linear(t, mx - max(rem, 0), 0, mx), facts, match_id=r.match_id,
                        members=[(g.scorer_member_id, "SUBJECT")] + ([(g.assist_member_id, "ASSIST")] if g.assist_member_id else []))
        # COMEBACK_WIN
        t = "COMEBACK_WIN"
        if ctx.enabled(t):
            deficit = _max_deficit(r)
            mn = ctx.p(t, "min_deficit", 2)
            if deficit >= mn:
                winners = [mid for mid, tid in r.members.items() if tid == r.win_team_id]
                scorers = sorted({x.scorer_member_id for x in r.goals
                                  if x.team_id == r.win_team_id and x.scorer_member_id and not x.own_goal})
                ctx.add(t, ctx.imp_linear(t, deficit, mn, ctx.p(t, "max_deficit_signal", 4)),
                        {"winnerTeam": code(r.win_team_id), "maxDeficit": deficit, **score_text(r),
                         "winnerScorers": [ctx.person(x) for x in scorers]},
                        match_id=r.match_id, members=[(x, "TEAM") for x in scorers or winners[:3]])
        # UPSET_WIN
        t = "UPSET_WIN"
        if ctx.enabled(t) and r.win_team_id and r.expected_a is not None:
            exp_w = r.expected_a if r.win_team_id == r.team_a_id else 1 - r.expected_a
            mx = ctx.p(t, "max_expected", 0.4)
            if exp_w <= mx:
                scorers = sorted({x.scorer_member_id for x in r.goals
                                  if x.team_id == r.win_team_id and x.scorer_member_id and not x.own_goal})
                ctx.add(t, ctx.imp_linear(t, mx - exp_w, 0, mx - ctx.p(t, "min_expected_signal", 0.2)),
                        {"winnerTeam": code(r.win_team_id), "underdogWin": True, **score_text(r),
                         "winnerScorers": [ctx.person(x) for x in scorers]},
                        match_id=r.match_id, members=[(x, "TEAM") for x in scorers])
        # HAT_TRICK
        t = "HAT_TRICK"
        if ctx.enabled(t):
            mn = ctx.p(t, "min_goals", 3)
            for mid in r.members:
                n = r.member_goals(mid)
                if n >= mn:
                    ctx.add(t, ctx.imp_step(t, n - mn, 10),
                            {"member": ctx.person(mid), "goals": n, "result": r.result_of(mid), **score_text(r)},
                            match_id=r.match_id, members=[(mid, "SUBJECT")])

    # 일정 단위
    tot_before = member_totals(before)
    tot_after = member_totals(upto)
    today_players = sorted({mid for r in today for mid in r.members})
    tot_today = member_totals(today)
    for mid in today_players:
        # MILESTONE_ACHIEVED
        t = "MILESTONE_ACHIEVED"
        if ctx.enabled(t):
            ms = _milestones(ctx, t)
            b, a = tot_before.get(mid), tot_after.get(mid)
            for metric in ("games", "goals", "assists"):
                vb = getattr(b, metric) if b else 0
                va = getattr(a, metric) if a else 0
                crossed = [m for m in ms if vb < m <= va]
                if crossed:
                    m = crossed[-1]
                    ctx.add(t, ctx.imp_linear(t, m, ms[0], ms[-1]),
                            {"member": ctx.person(mid), "metric": metric, "metricLabel": METRIC_LABEL[metric],
                             "milestone": m, "total": va}, members=[(mid, "SUBJECT")])
        # WIN_STREAK (오늘 마지막 경기까지 이어진 연승)
        t = "WIN_STREAK"
        if ctx.enabled(t):
            streak = win_streak(upto, mid)
            mn = ctx.p(t, "minimum_streak", 3)
            last_today = [r for r in today if mid in r.members][-1]
            if streak >= mn and last_today.result_of(mid) == "W":
                ctx.add(t, ctx.imp_step(t, streak - mn, ctx.p(t, "importance_per_extra_win", 8)),
                        {"member": ctx.person(mid), "streak": streak, "streakUnit": "경기", "ongoing": True},
                        members=[(mid, "SUBJECT")])
        # SCORING_STREAK
        t = "SCORING_STREAK"
        if ctx.enabled(t) and tot_today.get(mid) and tot_today[mid].goals > 0:
            streak = scoring_session_streak(upto, mid)
            mn = ctx.p(t, "minimum_streak", 3)
            if streak >= mn:
                ctx.add(t, ctx.imp_step(t, streak - mn, ctx.p(t, "importance_per_extra", 8)),
                        {"member": ctx.person(mid), "streak": streak, "streakUnit": "일정",
                         "goalsToday": tot_today[mid].goals}, members=[(mid, "SUBJECT")])
        # RETURN_PLAYER_RESULT
        t = "RETURN_PLAYER_RESULT"
        last = last_played_date(before, mid)
        if ctx.enabled(t) and last:
            days = (session.session_date - last).days
            th = ctx.p(t, "threshold_days", 30)
            if days >= th:
                td = tot_today.get(mid)
                ctx.add(t, ctx.imp_linear(t, days, th, ctx.p(t, "max_days", 120)),
                        {"member": ctx.person(mid), "daysSinceLastAppearance": days,
                         "gamesToday": td.games if td else 0, "winsToday": td.wins if td else 0,
                         "drawsToday": td.draws if td else 0, "lossesToday": td.losses if td else 0,
                         "goalsToday": td.goals if td else 0, "assistsToday": td.assists if td else 0},
                        members=[(mid, "SUBJECT")])

    # TITLE_AWARDED (이번 마감으로 확정된 자동 타이틀)
    t = "TITLE_AWARDED"
    if ctx.enabled(t):
        rows = db.execute(
            select(MemberTitle, TitleType).join(TitleType, TitleType.title_type_id == MemberTitle.title_type_id)
            .where(MemberTitle.club_id == club_id, MemberTitle.session_id == session.session_id,
                   MemberTitle.cancelled_yn.is_(False))
        ).all()
        for mt, tt in rows:
            ctx.add(t, ctx.types[t].base_importance,
                    {"member": ctx.person(mt.member_id), "titleName": tt.title_name,
                     "periodStart": mt.period_start.isoformat(), "periodEnd": mt.period_end.isoformat(),
                     **({k: v for k, v in (mt.facts_json or {}).items()})},
                    members=[(mt.member_id, "SUBJECT")])
    db.flush()
    return ctx.created


def session_summary(db: Session, club_id: int, session: ClubSession) -> dict:
    """마감 기사용 경기 결과 요약(Backend 계산 사실)."""
    teams = {t.session_team_id: t.team_code for t in db.scalars(select(SessionTeam).where(SessionTeam.session_id == session.session_id))}
    recs = load_history(db, club_id, session_ids=[session.session_id])
    names = {m.member_id: m.name for m in db.scalars(select(Member).where(Member.club_id == club_id))}
    tot = member_totals(recs)
    scorers = sorted(((mid, t.goals) for mid, t in tot.items() if t.goals > 0), key=lambda x: -x[1])
    team_record: dict[str, dict] = {}
    for r in recs:
        for tid in (r.team_a_id, r.team_b_id):
            rec = team_record.setdefault(teams.get(tid), {"wins": 0, "draws": 0, "losses": 0})
            if r.win_team_id is None:
                rec["draws"] += 1
            elif r.win_team_id == tid:
                rec["wins"] += 1
            else:
                rec["losses"] += 1
    return {
        "totalMatches": len(recs),
        "matches": [{"gameNo": r.game_no, "teamA": teams.get(r.team_a_id), "teamB": teams.get(r.team_b_id),
                     "scoreA": r.score_a, "scoreB": r.score_b,
                     "winner": teams.get(r.win_team_id) if r.win_team_id else None} for r in recs],
        "teamRecords": team_record,
        "topScorers": [{"name": names.get(mid), "goals": g} for mid, g in scorers[:5]],
    }


__all__ = ["generate_pre_insights", "generate_post_insights", "session_summary", "date"]
