"""원정 경기 기록(내부 기록과 완전히 분리된 집계).

원정 경기 일정(SESSION.AWAY_YN)의 확정 경기만 읽는다. TEAM_A = 우리 팀, TEAM_B = 원정팀(선수 없음).
- 전체 · 상대별 전적(우리 기준 승 · 무 · 패, 득점 · 실점)
- 상대별 상세(그 팀과의 일정 · 경기 점수 + 그 팀 상대로 우리 선수 골 · 도움 순위)
- 선수별 원정 기록(출전 경기 · 일정, 승 · 무 · 패, 골 · 도움 · 자책)
파생 테이블 없이 원본(MATCH_GAME · MATCH_MEMBER · MATCH_EVENT)에서 바로 계산한다(원정 경기 수가 적다).
"""
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import NotFound
from app.models import ClubSession, Member, OpponentTeam
from app.services.common import deleted_member_ids
from app.services.history import MatchRecord, load_history, member_totals, our_record


def _sessions(db: Session, club_id: int) -> dict[int, ClubSession]:
    return {s.session_id: s for s in db.scalars(select(ClubSession).where(
        ClubSession.club_id == club_id, ClubSession.away_yn.is_(True), ClubSession.deleted_at.is_(None)))}


def _records(db: Session, club_id: int, sessions: dict[int, ClubSession]) -> list[MatchRecord]:
    return [r for r in load_history(db, club_id, away=True) if r.session_id in sessions]


def _rate(n: int, d: int) -> float | None:
    return round(n / d, 4) if d else None


def away_overview(db: Session, club_id: int, recent_n: int = 10) -> dict:
    """기록 탭 '원정' 영역: 전체 전적 · 상대별 전적 · 최근 원정 일정 · 선수별 원정 기록."""
    sessions = _sessions(db, club_id)
    records = _records(db, club_id, sessions)

    by_opp: dict[int | None, dict] = {}  # 원정팀 목록 ID별
    by_session: dict[int, list[MatchRecord]] = {}
    for r in records:
        by_session.setdefault(r.session_id, []).append(r)
    for sid, recs in by_session.items():
        s = sessions[sid]
        o = by_opp.setdefault(s.opponent_id, {"opponentId": s.opponent_id, "opponentName": s.opponent_name,
                                              "sessions": 0, "lastDate": None, "records": []})
        o["sessions"] += 1
        o["records"].extend(recs)
        if o["lastDate"] is None or s.session_date >= o["lastDate"]:
            o["lastDate"], o["opponentName"] = s.session_date, s.opponent_name  # 최근 표기를 대표 이름으로
    opponents = sorted(
        ({"opponentId": o["opponentId"], "opponentName": o["opponentName"], "sessions": o["sessions"],
          "lastDate": o["lastDate"],
          **our_record(o["records"])} for o in by_opp.values()),
        key=lambda x: (x["lastDate"], x["opponentName"] or ""), reverse=True)

    recent = []
    for sid in sorted(by_session, key=lambda x: (sessions[x].session_date, x), reverse=True)[:recent_n]:
        s = sessions[sid]
        recent.append({"sessionId": sid, "sessionDate": s.session_date, "opponentName": s.opponent_name,
                       **our_record(by_session[sid])})

    return {"summary": {"sessions": len(by_session), **our_record(records)},
            "opponents": opponents, "recent": recent, "members": _member_rows(db, club_id, records)}


def _member_rows(db: Session, club_id: int, records: list[MatchRecord]) -> list[dict]:
    """선수별 원정 기록(골 → 도움 → 경기 수 순). 삭제한 선수는 뺀다."""
    totals = member_totals(records)
    deleted = deleted_member_ids(db, club_id)
    names = {m.member_id: m.name for m in db.scalars(select(Member).where(Member.club_id == club_id))}
    return sorted(
        ({"memberId": mid, "name": names.get(mid), "games": t.games, "sessions": len(t.sessions),
          "wins": t.wins, "draws": t.draws, "losses": t.losses, "winRate": _rate(t.wins, t.games),
          "goals": t.goals, "assists": t.assists, "ownGoals": t.own_goals,
          "lastPlayedDate": t.last_played_date}
         for mid, t in totals.items() if mid not in deleted and t.games > 0),
        key=lambda x: (-x["goals"], -x["assists"], -x["games"], x["name"] or ""))


def away_opponent(db: Session, club_id: int, opponent_id: int) -> dict:
    """기록 탭 '원정' → 상대 팀 하나: 그 팀과의 원정 일정 · 경기 점수(최근 순) + 그 팀 상대 우리 선수 기록.
    숨긴 팀도 볼 수 있다(지난 전적은 그대로)."""
    o = db.scalar(select(OpponentTeam).where(OpponentTeam.opponent_id == opponent_id, OpponentTeam.club_id == club_id))
    if not o:
        raise NotFound("원정팀을 찾을 수 없습니다.", "OPPONENT_NOT_FOUND")
    sessions = {sid: s for sid, s in _sessions(db, club_id).items() if s.opponent_id == opponent_id}
    records = _records(db, club_id, sessions)
    by_session: dict[int, list[MatchRecord]] = {}
    for r in records:
        by_session.setdefault(r.session_id, []).append(r)
    rows = []
    for sid in sorted(by_session, key=lambda x: (sessions[x].session_date, x), reverse=True):
        s, recs = sessions[sid], by_session[sid]
        rows.append({
            "sessionId": sid, "sessionDate": s.session_date, "title": s.title, "location": s.location,
            **our_record(recs),
            "matches": [{"matchId": r.match_id, "gameNo": r.game_no, "scoreFor": r.score_a, "scoreAgainst": r.score_b,
                         "result": "W" if r.score_a > r.score_b else "D" if r.score_a == r.score_b else "L"}
                        for r in sorted(recs, key=lambda x: x.game_no)],
        })
    return {"opponent": {"opponentId": o.opponent_id, "name": o.name, "active": o.active_yn},
            "summary": {"sessions": len(by_session), **our_record(records)},
            "sessions": rows, "members": _member_rows(db, club_id, records)}


def away_member(db: Session, club_id: int, member_id: int, recent_n: int = 5) -> dict:
    """선수 상세의 '원정' 영역: 원정 통산 + 최근 원정 경기."""
    sessions = _sessions(db, club_id)
    mine = [r for r in _records(db, club_id, sessions) if member_id in r.members]
    t = member_totals(mine).get(member_id)
    return {
        "games": t.games if t else 0, "sessions": len(t.sessions) if t else 0,
        "wins": t.wins if t else 0, "draws": t.draws if t else 0, "losses": t.losses if t else 0,
        "winRate": _rate(t.wins, t.games) if t else None,
        "goals": t.goals if t else 0, "assists": t.assists if t else 0, "ownGoals": t.own_goals if t else 0,
        "recent": [
            {"matchId": r.match_id, "sessionDate": r.session_date, "gameNo": r.game_no,
             "opponentName": sessions[r.session_id].opponent_name, "result": r.result_of(member_id),
             "scoreFor": r.score_a, "scoreAgainst": r.score_b,
             "goals": r.member_goals(member_id), "assists": r.member_assists(member_id)}
            for r in reversed(mine[-recent_n:])
        ],
    }


__all__ = ["away_overview", "away_opponent", "away_member"]
