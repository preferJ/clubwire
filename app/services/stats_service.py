"""개인 통계 / Pair 통계 (파생 데이터 재구성 + 조회)."""
from collections import defaultdict
from datetime import date
from itertools import combinations

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.models import Member, MemberPairStat, MemberStatSummary, MemberTitle, TitleType
from app.services.common import lock_club
from app.services.history import MatchRecord, load_history, member_totals


def rebuild_member_stats(db: Session, club_id: int) -> None:
    lock_club(db, club_id)
    records = load_history(db, club_id)
    totals = member_totals(records)

    title_rows = db.execute(
        select(MemberTitle.member_id, TitleType.counts_as_mvp_yn)
        .join(TitleType, TitleType.title_type_id == MemberTitle.title_type_id)
        .where(MemberTitle.club_id == club_id, MemberTitle.cancelled_yn.is_(False))
    ).all()
    mvp: dict[int, int] = defaultdict(int)
    titles: dict[int, int] = defaultdict(int)
    for mid, is_mvp in title_rows:
        titles[mid] += 1
        if is_mvp:
            mvp[mid] += 1

    db.execute(delete(MemberStatSummary).where(MemberStatSummary.club_id == club_id))
    for mid in db.scalars(select(Member.member_id).where(Member.club_id == club_id)):
        t = totals.get(mid)
        db.add(
            MemberStatSummary(
                member_id=mid, club_id=club_id,
                games=t.games if t else 0, wins=t.wins if t else 0, draws=t.draws if t else 0,
                losses=t.losses if t else 0, goals=t.goals if t else 0, assists=t.assists if t else 0,
                own_goals=t.own_goals if t else 0, mvp_count=mvp.get(mid, 0), title_count=titles.get(mid, 0),
                sessions_attended=len(t.sessions) if t else 0, last_played_date=t.last_played_date if t else None,
            )
        )
    db.flush()


def aggregate_pairs(records: list[MatchRecord]) -> dict[tuple[int, int], dict]:
    """확정 경기 기록 → Pair 집계(순수 계산). PRE Insight도 '그 일정 이전 기록'으로 같은 함수를 쓴다."""
    stats: dict[tuple[int, int], dict] = {}

    def pair(a: int, b: int) -> dict:
        key = (a, b) if a < b else (b, a)
        if key not in stats:
            stats[key] = dict(co=0, same=0, since=0, same_m=0, same_w=0, same_d=0, opp=0, low_w=0, high_w=0,
                              last_same=None, last_opp=None)
        return stats[key]

    # 경기 단위
    sessions: dict[int, dict] = {}
    for r in records:
        sess = sessions.setdefault(r.session_id, {"date": r.session_date, "teams": defaultdict(set)})
        for mid, team in r.members.items():
            sess["teams"][mid].add(team)
        for (a, ta), (b, tb) in combinations(sorted(r.members.items()), 2):
            p = pair(a, b)
            if ta == tb:
                p["same_m"] += 1
                if r.win_team_id is None:
                    p["same_d"] += 1
                elif r.win_team_id == ta:
                    p["same_w"] += 1
            else:
                p["opp"] += 1
                p["last_opp"] = r.session_date
                if r.win_team_id is not None:
                    low_team = ta  # a < b (sorted)
                    if r.win_team_id == low_team:
                        p["low_w"] += 1
                    else:
                        p["high_w"] += 1

    # 세션 단위(시간순)
    for sid in sorted(sessions, key=lambda s: (sessions[s]["date"], s)):
        sess = sessions[sid]
        players = sorted(sess["teams"])
        for a, b in combinations(players, 2):
            p = pair(a, b)
            p["co"] += 1
            if sess["teams"][a] & sess["teams"][b]:
                p["same"] += 1
                p["since"] = 0
                p["last_same"] = sess["date"]
            else:
                p["since"] += 1

    return stats


def rebuild_pair_stats(db: Session, club_id: int) -> None:
    """MATCH_MEMBER(실제 출전) 기준 Pair 집계.

    - 세션 단위: 둘 다 그 세션 확정 경기에 뛰었으면 CO_ATTENDANCE +1,
                 같은 SESSION_TEAM으로 뛴 적이 있으면 SAME_TEAM +1
    - 경기 단위: 같은 편이면 SAME_TEAM_MATCH, 실제로 맞붙었으면 OPPONENT_MATCH
      (3팀 이상일 때 대기 팀 선수는 상대가 아니다)
    """
    lock_club(db, club_id)
    stats = aggregate_pairs(load_history(db, club_id))

    db.execute(delete(MemberPairStat).where(MemberPairStat.club_id == club_id))
    for (a, b), p in stats.items():
        db.add(
            MemberPairStat(
                member_id_low=a, member_id_high=b, club_id=club_id,
                co_attendance_count=p["co"], same_team_count=p["same"], co_attendance_since_same_team=p["since"],
                same_team_match_count=p["same_m"], same_team_win_count=p["same_w"], same_team_draw_count=p["same_d"],
                opponent_match_count=p["opp"], opponent_low_win_count=p["low_w"], opponent_high_win_count=p["high_w"],
                last_same_team_at=p["last_same"], last_opponent_at=p["last_opp"],
            )
        )
    db.flush()


def rebuild_all_stats(db: Session, club_id: int) -> None:
    rebuild_member_stats(db, club_id)
    rebuild_pair_stats(db, club_id)


def pair_map(db: Session, club_id: int) -> dict[tuple[int, int], MemberPairStat]:
    return {(p.member_id_low, p.member_id_high): p
            for p in db.scalars(select(MemberPairStat).where(MemberPairStat.club_id == club_id))}


def pair_get(pairs: dict[tuple[int, int], MemberPairStat], a: int, b: int) -> MemberPairStat | None:
    return pairs.get((a, b) if a < b else (b, a))


# ------------------------------------------------------------------ 조회
def _rate(n: int, d: int) -> float | None:
    return round(n / d, 4) if d else None


def member_summaries(db: Session, club_id: int) -> list[dict]:
    rows = db.execute(
        select(Member, MemberStatSummary)
        .join(MemberStatSummary, MemberStatSummary.member_id == Member.member_id, isouter=True)
        .where(Member.club_id == club_id)
        .order_by(Member.display_order, Member.name)
    ).all()
    out = []
    for m, s in rows:
        out.append(_summary_dict(m, s))
    return out


def _summary_dict(m: Member, s: MemberStatSummary | None) -> dict:
    g = s.games if s else 0
    return {
        "memberId": m.member_id, "name": m.name, "active": m.active_yn,
        "games": g, "wins": s.wins if s else 0, "draws": s.draws if s else 0, "losses": s.losses if s else 0,
        "winRate": _rate(s.wins, g) if s else None,
        "goals": s.goals if s else 0, "assists": s.assists if s else 0, "ownGoals": s.own_goals if s else 0,
        "titleCount": s.title_count if s else 0,
        "sessionsAttended": s.sessions_attended if s else 0,
        "lastPlayedDate": s.last_played_date if s else None,
    }


def member_detail(db: Session, club_id: int, member: Member, recent_n: int = 5, top_n: int = 5) -> dict:
    s = db.get(MemberStatSummary, member.member_id)
    records = load_history(db, club_id)
    mine = [r for r in records if member.member_id in r.members]
    recent = [
        {"matchId": r.match_id, "sessionDate": r.session_date, "gameNo": r.game_no,
         "result": r.result_of(member.member_id), "goals": r.member_goals(member.member_id),
         "assists": r.member_assists(member.member_id)}
        for r in reversed(mine[-recent_n:])
    ]
    names = {m.member_id: m.name for m in db.scalars(select(Member).where(Member.club_id == club_id))}
    pairs = [p for p in pair_map(db, club_id).values() if member.member_id in (p.member_id_low, p.member_id_high)]

    def other(p: MemberPairStat) -> int:
        return p.member_id_high if p.member_id_low == member.member_id else p.member_id_low

    teammates = sorted([p for p in pairs if p.same_team_match_count > 0],
                       key=lambda p: (-p.same_team_match_count, -p.same_team_win_count))[:top_n]
    opponents = sorted([p for p in pairs if p.opponent_match_count > 0],
                       key=lambda p: -p.opponent_match_count)[:top_n]
    best_duo = sorted([p for p in pairs if p.same_team_match_count >= 3],
                      key=lambda p: (-(p.same_team_win_count / p.same_team_match_count), -p.same_team_match_count))[:top_n]

    def my_wins_vs(p: MemberPairStat) -> int:
        return p.opponent_low_win_count if p.member_id_low == member.member_id else p.opponent_high_win_count

    def their_wins_vs(p: MemberPairStat) -> int:
        return p.opponent_high_win_count if p.member_id_low == member.member_id else p.opponent_low_win_count

    return {
        "summary": _summary_dict(member, s),
        "profile": {"joinedAt": member.joined_at, "birthYear": member.birth_year},  # 관리자가 입력한 선수 정보(공개)
        "recentForm": recent,
        "frequentTeammates": [
            {"memberId": other(p), "name": names.get(other(p)), "matches": p.same_team_match_count,
             "wins": p.same_team_win_count, "draws": p.same_team_draw_count,
             "winRate": _rate(p.same_team_win_count, p.same_team_match_count),
             "lastSameTeamDate": p.last_same_team_at} for p in teammates
        ],
        "bestWinRateTeammates": [
            {"memberId": other(p), "name": names.get(other(p)), "matches": p.same_team_match_count,
             "winRate": _rate(p.same_team_win_count, p.same_team_match_count)} for p in best_duo
        ],
        "frequentOpponents": [
            {"memberId": other(p), "name": names.get(other(p)), "matches": p.opponent_match_count,
             "wins": my_wins_vs(p), "losses": their_wins_vs(p),
             "draws": p.opponent_match_count - my_wins_vs(p) - their_wins_vs(p),
             "lastOpponentDate": p.last_opponent_at} for p in opponents
        ],
    }


def head_to_head(db: Session, club_id: int, a: int, b: int) -> dict:
    p = pair_get(pair_map(db, club_id), a, b)
    if not p:
        return {"memberIdA": a, "memberIdB": b, "coAttendance": 0, "sameTeamSessions": 0, "sameTeamMatches": 0,
                "sameTeamWins": 0, "opponentMatches": 0, "winsA": 0, "winsB": 0}
    wins_a = p.opponent_low_win_count if a < b else p.opponent_high_win_count
    wins_b = p.opponent_high_win_count if a < b else p.opponent_low_win_count
    return {
        "memberIdA": a, "memberIdB": b, "coAttendance": p.co_attendance_count,
        "sameTeamSessions": p.same_team_count, "sameTeamMatches": p.same_team_match_count,
        "sameTeamWins": p.same_team_win_count, "sameTeamWinRate": _rate(p.same_team_win_count, p.same_team_match_count),
        "opponentMatches": p.opponent_match_count, "winsA": wins_a, "winsB": wins_b,
        "lastSameTeamDate": p.last_same_team_at, "lastOpponentDate": p.last_opponent_at,
    }


__all__ = ["rebuild_member_stats", "rebuild_pair_stats", "rebuild_all_stats", "pair_map", "pair_get",
           "member_summaries", "member_detail", "head_to_head", "date"]
