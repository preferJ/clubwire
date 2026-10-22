"""일정(SESSION) / 참석자 / 게스트."""
from datetime import date

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.database import emit
from app.core.errors import BadRequest, Conflict
from app.core.timeutil import to_iso, utcnow
from app.models import (
    ClubSession,
    MatchEvent,
    MatchGame,
    Member,
    SessionGuest,
    SessionMember,
    SessionTeam,
    SessionTeamMember,
)
from app.models.enums import AttendanceStatus, GameStatus, SessionStatus
from app.services.common import get_member, get_session, guard_after_closed, guard_not_closed, session_teams
from app.strategies.team_generation import balance_label, spread_percent


# ------------------------------------------------------------------ 일정
def create_session(db: Session, club_id: int, session_date: date, title: str | None, location: str | None) -> ClubSession:
    guard_after_closed(db, club_id, (session_date, 2**63))  # 새 일정 ID는 항상 기존보다 크다
    s = ClubSession(club_id=club_id, session_date=session_date,
                    title=title or "정기 경기", location=location,
                    status=SessionStatus.OPEN)
    db.add(s)
    db.flush()
    emit(db, club_id, "SESSION_UPDATED", {"sessionId": s.session_id, "status": s.status})
    db.commit()
    return s


def update_session(db: Session, club_id: int, session_id: int, **fields) -> ClubSession:
    s = get_session(db, club_id, session_id, lock=True)
    guard_not_closed(s)
    if "session_date" in fields and fields["session_date"] is not None:
        if s.status != SessionStatus.OPEN:
            raise Conflict("확정된 일정은 날짜를 바꿀 수 없습니다.", "SESSION_CONFIRMED")
        guard_after_closed(db, club_id, (fields["session_date"], s.session_id))
        s.session_date = fields["session_date"]
    for k in ("title", "location"):
        if fields.get(k) is not None:
            setattr(s, k, fields[k])
    emit(db, club_id, "SESSION_UPDATED", {"sessionId": s.session_id, "status": s.status})
    db.commit()
    return s


def cancel_session(db: Session, club_id: int, session_id: int) -> ClubSession:
    s = get_session(db, club_id, session_id, lock=True)
    guard_not_closed(s)
    started = db.scalar(
        select(func.count()).select_from(MatchGame).where(
            MatchGame.session_id == session_id, MatchGame.game_status != GameStatus.CANCELLED,
            MatchGame.started_at.is_not(None))
    )
    if started:
        raise Conflict("이미 경기가 진행된 일정은 취소할 수 없습니다. [일정마감]을 사용하세요.", "SESSION_HAS_MATCHES")
    s.status = SessionStatus.CANCELLED
    s.cancelled_at = utcnow()
    emit(db, club_id, "SESSION_UPDATED", {"sessionId": s.session_id, "status": s.status})
    db.commit()
    return s


def list_sessions(db: Session, club_id: int, limit: int = 30, before: date | None = None) -> list[ClubSession]:
    stmt = select(ClubSession).where(ClubSession.club_id == club_id)
    if before:
        stmt = stmt.where(ClubSession.session_date < before)
    return list(db.scalars(stmt.order_by(ClubSession.session_date.desc(), ClubSession.session_id.desc()).limit(limit)))


# ------------------------------------------------------------------ 참석자 (팀 확정 전)
def _require_open(s: ClubSession) -> None:
    guard_not_closed(s)
    if s.status != SessionStatus.OPEN:
        raise Conflict("팀이 확정된 뒤에는 '팀 수동 변경'으로 추가/제외하세요.", "SESSION_CONFIRMED")


def add_attendees(db: Session, club_id: int, session_id: int, member_ids: list[int]) -> list[SessionMember]:
    s = get_session(db, club_id, session_id, lock=True)
    _require_open(s)
    if not member_ids:
        raise BadRequest("참석자를 선택하세요.")
    existing = {sm.member_id: sm for sm in db.scalars(select(SessionMember).where(SessionMember.session_id == session_id))}
    for mid in dict.fromkeys(member_ids):
        get_member(db, club_id, mid, active_only=True)
        sm = existing.get(mid)
        if sm:
            sm.attendance_status = AttendanceStatus.ATTENDING
        else:
            db.add(SessionMember(session_id=session_id, member_id=mid, attendance_status=AttendanceStatus.ATTENDING))
    emit(db, club_id, "SESSION_UPDATED", {"sessionId": session_id, "status": s.status})
    db.commit()
    return list(db.scalars(select(SessionMember).where(SessionMember.session_id == session_id)))


def remove_attendee(db: Session, club_id: int, session_id: int, member_id: int) -> None:
    s = get_session(db, club_id, session_id, lock=True)
    _require_open(s)
    sm = db.scalar(select(SessionMember).where(SessionMember.session_id == session_id, SessionMember.member_id == member_id))
    if sm:
        sm.attendance_status = AttendanceStatus.ABSENT  # 삭제 대신 상태 변경
    emit(db, club_id, "SESSION_UPDATED", {"sessionId": session_id, "status": s.status})
    db.commit()


def add_guests(db: Session, club_id: int, session_id: int, count: int = 1, names: list[str] | None = None) -> list[SessionGuest]:
    s = get_session(db, club_id, session_id, lock=True)
    _require_open(s)
    names = [n.strip() for n in (names or []) if n and n.strip()]
    n_total = max(count, len(names))
    if n_total < 1 or n_total > 20:
        raise BadRequest("게스트 수가 올바르지 않습니다.")
    current = db.scalar(select(func.count()).select_from(SessionGuest).where(SessionGuest.session_id == session_id)) or 0
    created = []
    for i in range(n_total):
        g = SessionGuest(session_id=session_id, guest_name=names[i] if i < len(names) else f"게스트{current + i + 1}")
        db.add(g)
        created.append(g)
    emit(db, club_id, "SESSION_UPDATED", {"sessionId": session_id, "status": s.status})
    db.commit()
    return created


def remove_guest(db: Session, club_id: int, session_id: int, guest_id: int) -> None:
    s = get_session(db, club_id, session_id, lock=True)
    _require_open(s)
    g = db.scalar(select(SessionGuest).where(SessionGuest.guest_id == guest_id, SessionGuest.session_id == session_id))
    if g:
        g.active_yn = False
    db.commit()


def attending_member_ids(db: Session, session_id: int) -> list[int]:
    return list(
        db.scalars(
            select(SessionMember.member_id)
            .join(Member, Member.member_id == SessionMember.member_id)
            .where(SessionMember.session_id == session_id,
                   SessionMember.attendance_status == AttendanceStatus.ATTENDING)
            .order_by(SessionMember.member_id)
        )
    )


def active_guests(db: Session, session_id: int) -> list[SessionGuest]:
    return list(db.scalars(select(SessionGuest).where(SessionGuest.session_id == session_id,
                                                      SessionGuest.active_yn.is_(True)).order_by(SessionGuest.guest_id)))


# ------------------------------------------------------------------ 조회
def team_rosters(db: Session, session_id: int) -> dict[int, dict]:
    """팀별 현재 명단(멤버 + 게스트)."""
    teams = session_teams(db, session_id)
    out = {t.session_team_id: {"team": t, "members": [], "guests": []} for t in teams}
    rows = db.execute(
        select(SessionTeamMember, Member)
        .join(Member, Member.member_id == SessionTeamMember.member_id)
        .where(SessionTeamMember.session_id == session_id, SessionTeamMember.active_yn.is_(True))
        .order_by(Member.name)
    ).all()
    for stm, m in rows:
        if stm.session_team_id in out:
            out[stm.session_team_id]["members"].append((stm, m))
    for g in active_guests(db, session_id):
        if g.session_team_id in out:
            out[g.session_team_id]["guests"].append(g)
    return out


def serialize_session(db: Session, s: ClubSession, *, detail: bool = False, admin: bool = False) -> dict:
    data = {
        "sessionId": s.session_id, "sessionDate": s.session_date, "title": s.title, "location": s.location,
        "status": s.status, "teamCount": s.team_count,
        "confirmedAt": to_iso(s.confirmed_at), "closedAt": to_iso(s.closed_at),
    }
    if not detail:
        data["attendeeCount"] = db.scalar(select(func.count()).select_from(SessionMember).where(
            SessionMember.session_id == s.session_id,
            SessionMember.attendance_status == AttendanceStatus.ATTENDING)) or 0
        data["guestCount"] = db.scalar(select(func.count()).select_from(SessionGuest).where(
            SessionGuest.session_id == s.session_id, SessionGuest.active_yn.is_(True))) or 0
        return data
    att = db.execute(
        select(SessionMember, Member)
        .join(Member, Member.member_id == SessionMember.member_id)
        .where(SessionMember.session_id == s.session_id, SessionMember.attendance_status == AttendanceStatus.ATTENDING)
        .order_by(Member.name)
    ).all()
    data["attendees"] = [{"memberId": m.member_id, "name": m.name} for _, m in att]
    guests = active_guests(db, s.session_id)
    data["guests"] = [{"guestId": g.guest_id, "name": g.guest_name, "sessionTeamId": g.session_team_id} for g in guests]
    data["headcount"] = len(att) + len(guests)

    rosters = team_rosters(db, s.session_id)
    teams = []
    strengths = []
    for info in rosters.values():
        t: SessionTeam = info["team"]
        if t.team_strength_snapshot is not None:
            strengths.append(t.team_strength_snapshot)
        team = {
            "sessionTeamId": t.session_team_id, "teamCode": t.team_code, "displayName": t.display_name,
            "members": [{"memberId": m.member_id, "name": m.name, "assignType": stm.assign_type} for stm, m in info["members"]],
            "guests": [{"guestId": g.guest_id, "name": g.guest_name} for g in info["guests"]],
            "headcount": len(info["members"]) + len(info["guests"]),
        }
        if admin:  # 팀 편성 정보(팀 단위)만. 선수별 Rating은 DB에서만 확인
            team["avgRatingSnapshot"] = t.avg_rating_snapshot
            team["strengthSnapshot"] = t.team_strength_snapshot
        teams.append(team)
    data["teams"] = teams
    data["balanceLabel"] = balance_label(spread_percent(strengths)) if len(strengths) >= 2 else None

    matches = db.scalars(select(MatchGame).where(MatchGame.session_id == s.session_id).order_by(MatchGame.game_no))
    code = {info["team"].session_team_id: info["team"].team_code for info in rosters.values()}
    data["matches"] = [
        {"matchId": m.match_id, "gameNo": m.game_no, "status": m.game_status, "finalized": m.finalized_at is not None,
         "teamA": {"sessionTeamId": m.team_a_id, "teamCode": code.get(m.team_a_id), "score": m.score_a},
         "teamB": {"sessionTeamId": m.team_b_id, "teamCode": code.get(m.team_b_id), "score": m.score_b},
         "winTeamId": m.win_team_id, "startedAt": to_iso(m.started_at), "finishedAt": to_iso(m.finished_at)}
        for m in matches
    ]
    return data


def session_summary(db: Session, club_id: int, session_id: int) -> dict:
    """[일정마감] 화면용 요약. 확정 전(FINISHED) 경기도 포함해 오늘 기록을 보여준다."""
    s = get_session(db, club_id, session_id)
    teams = session_teams(db, session_id)
    code = {t.session_team_id: t.team_code for t in teams}
    matches = list(db.scalars(select(MatchGame).where(MatchGame.session_id == session_id,
                                                      MatchGame.game_status != GameStatus.CANCELLED)
                              .order_by(MatchGame.game_no)))
    finished = [m for m in matches if m.game_status == GameStatus.FINISHED]
    records = {t.session_team_id: {"sessionTeamId": t.session_team_id, "teamCode": t.team_code,
                                   "wins": 0, "draws": 0, "losses": 0} for t in teams}
    for m in finished:
        for tid, mine, theirs in ((m.team_a_id, m.score_a, m.score_b), (m.team_b_id, m.score_b, m.score_a)):
            r = records.get(tid)
            if r is None:
                continue
            r["wins" if mine > theirs else "draws" if mine == theirs else "losses"] += 1
    goals: dict[int, int] = {}
    assists: dict[int, int] = {}
    ids = [m.match_id for m in finished]
    if ids:
        for e in db.scalars(select(MatchEvent).where(MatchEvent.match_id.in_(ids), MatchEvent.event_type == "GOAL",
                                                     MatchEvent.cancelled_yn.is_(False))):
            if e.scorer_member_id and not e.own_goal_yn:
                goals[e.scorer_member_id] = goals.get(e.scorer_member_id, 0) + 1
            if e.assist_member_id:
                assists[e.assist_member_id] = assists.get(e.assist_member_id, 0) + 1
    names = {m.member_id: m.name for m in db.scalars(select(Member).where(Member.club_id == club_id))}

    def top(d: dict[int, int]) -> list[dict]:
        return [{"memberId": k, "name": names.get(k), "count": v}
                for k, v in sorted(d.items(), key=lambda x: (-x[1], names.get(x[0], "")))[:5]]

    return {
        "sessionId": s.session_id, "status": s.status,
        "finishedCount": len(finished),
        "unfinalizedCount": sum(1 for m in finished if m.finalized_at is None),
        "readyCount": sum(1 for m in matches if m.game_status == GameStatus.READY),
        "activeCount": sum(1 for m in matches if m.game_status in (GameStatus.RUNNING, GameStatus.PAUSED)),
        "totalGoals": sum(m.score_a + m.score_b for m in finished),
        "matches": [{"matchId": m.match_id, "gameNo": m.game_no, "status": m.game_status,
                     "finalized": m.finalized_at is not None,
                     "teamA": code.get(m.team_a_id), "teamB": code.get(m.team_b_id),
                     "scoreA": m.score_a, "scoreB": m.score_b} for m in matches],
        "teamRecords": list(records.values()),
        "topScorers": top(goals),
        "topAssists": top(assists),
    }
