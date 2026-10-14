"""경기 엔진: 다음 경기 생성(대진은 관리자 지정), LIVE 타이머, 골/도움/자책골, 종료, 확정(Finalize).

동시성
- 경기 상태/점수 변경은 MATCH_GAME 행을 SELECT … FOR UPDATE로 잠근 뒤 처리한다.
- 골 등록은 IDEMPOTENCY_KEY(UNIQUE MATCH_ID+KEY)로 더블클릭 중복을 막는다.
- 점수는 GOAL/GOAL_CANCEL 이벤트와 같은 트랜잭션에서만 바뀐다.
"""
import math
from datetime import datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.database import SessionLocal, emit
from app.core.errors import BadRequest, Conflict, NotFound
from app.core.timeutil import to_iso, utcnow
from app.models import (
    ClubSession,
    MatchEvent,
    MatchGame,
    MatchMember,
    Member,
    SessionGuest,
    SessionTeam,
    SessionTeamMember,
)
from app.models.enums import EndReason, EventType, GameStatus, SessionStatus
from app.services.common import (
    get_match,
    get_session,
    guard_after_closed,
    guard_not_closed,
    member_names,
    session_teams,
)
from app.services.config_service import load_config
from app.services.rating_service import current_states, match_key, rebuild_ratings
from app.services.stats_service import rebuild_all_stats
from app.strategies.match_order import PlayedMatch, match_order_strategy
from app.strategies.rating import expected_score, team_strength_strategy

ACTIVE_STATUSES = (GameStatus.READY, GameStatus.RUNNING, GameStatus.PAUSED)


# ------------------------------------------------------------------ 타이머 계산
def elapsed_seconds(m: MatchGame, now: datetime | None = None) -> float:
    if m.started_at is None:
        return 0.0
    if m.game_status == GameStatus.RUNNING:
        end = now or utcnow()
    elif m.game_status == GameStatus.PAUSED:
        end = m.paused_at or now or utcnow()
    elif m.finished_at is not None:
        end = m.finished_at
    else:
        end = now or utcnow()
    return max(0.0, (end - m.started_at).total_seconds() - (m.paused_seconds or 0.0))


def winner_of(m: MatchGame) -> int | None:
    if m.score_a > m.score_b:
        return m.team_a_id
    if m.score_b > m.score_a:
        return m.team_b_id
    return None


def _team_map(db: Session, session_id: int) -> dict[int, SessionTeam]:
    return {t.session_team_id: t for t in session_teams(db, session_id)}


def match_state(db: Session, m: MatchGame, teams: dict[int, SessionTeam] | None = None,
                now: datetime | None = None) -> dict:
    now = now or utcnow()
    teams = teams or _team_map(db, m.session_id)
    elapsed = elapsed_seconds(m, now)
    remaining = m.game_duration_sec - elapsed

    def team(tid: int, score: int) -> dict:
        t = teams.get(tid)
        return {"sessionTeamId": tid, "teamCode": t.team_code if t else None,
                "displayName": t.display_name if t else None, "score": score}

    return {
        "matchId": m.match_id, "sessionId": m.session_id, "gameNo": m.game_no, "status": m.game_status,
        "finalized": m.finalized_at is not None, "finalizedAt": to_iso(m.finalized_at),
        "teamA": team(m.team_a_id, m.score_a), "teamB": team(m.team_b_id, m.score_b),
        "durationSec": m.game_duration_sec, "elapsedSec": round(elapsed, 1),
        "remainingSec": round(max(0.0, remaining), 1), "overtimeSec": round(max(0.0, -remaining), 1),
        "startedAt": to_iso(m.started_at), "pausedAt": to_iso(m.paused_at), "pausedSeconds": round(m.paused_seconds or 0, 3),
        "finishedAt": to_iso(m.finished_at), "endReason": m.end_reason,
        "autoEnd": m.auto_end_yn, "earlyEndGoals": m.early_end_goals,
        "winTeamId": m.win_team_id if m.finalized_at else (winner_of(m) if m.game_status == GameStatus.FINISHED else None),
        "version": m.version, "serverTime": to_iso(now),
    }


def serialize_event(e: MatchEvent, names: dict[int, str]) -> dict:
    return {
        "eventId": e.event_id, "matchId": e.match_id, "eventType": e.event_type, "teamId": e.team_id,
        "scorerMemberId": e.scorer_member_id, "scorerName": names.get(e.scorer_member_id),
        "assistMemberId": e.assist_member_id, "assistName": names.get(e.assist_member_id),
        "memberId": e.member_id, "ownGoal": e.own_goal_yn, "guestGoal": e.guest_goal_yn,
        "elapsedSec": e.elapsed_sec, "remainingSec": e.remaining_sec, "refEventId": e.ref_event_id,
        "cancelled": e.cancelled_yn, "memo": e.memo, "createdAt": to_iso(e.created_at),
    }


def match_detail(db: Session, m: MatchGame) -> dict:
    teams = _team_map(db, m.session_id)
    data = match_state(db, m, teams)
    events = list(db.scalars(select(MatchEvent).where(MatchEvent.match_id == m.match_id).order_by(MatchEvent.event_id)))
    mms = list(db.scalars(select(MatchMember).where(MatchMember.match_id == m.match_id)))
    names = member_names(db, [x.member_id for x in mms] + [e.scorer_member_id for e in events]
                         + [e.assist_member_id for e in events] + [e.member_id for e in events])
    data["events"] = [serialize_event(e, names) for e in events]
    for key, tid in (("teamA", m.team_a_id), ("teamB", m.team_b_id)):
        data[key]["members"] = [{"memberId": x.member_id, "name": names.get(x.member_id)}
                                for x in mms if x.session_team_id == tid]
        data[key]["guestCount"] = db.scalar(select(func.count()).select_from(SessionGuest).where(
            SessionGuest.session_team_id == tid, SessionGuest.active_yn.is_(True))) or 0
    return data


def _emit_state(db: Session, club_id: int, m: MatchGame) -> None:
    emit(db, club_id, "MATCH_UPDATED", {"matchId": m.match_id, "sessionId": m.session_id, "match": match_state(db, m)})


def _event(db: Session, m: MatchGame, event_type: EventType, admin_id: int | None, **kw) -> MatchEvent:
    e = MatchEvent(match_id=m.match_id, event_type=event_type, admin_id=admin_id, **kw)
    db.add(e)
    db.flush()
    return e


# ------------------------------------------------------------------ 다음 경기(관리자 지정)
def _history(db: Session, session_id: int) -> list[MatchGame]:
    return list(db.scalars(select(MatchGame).where(MatchGame.session_id == session_id,
                                                   MatchGame.game_status != GameStatus.CANCELLED)
                           .order_by(MatchGame.game_no)))


def next_suggestion(db: Session, club_id: int, session_id: int) -> dict:
    """다음 경기 대진 화면용: 팀별 오늘 경기 수/연속 경기 수 + 추천 대진(가장 오래 쉰 두 팀)."""
    s = get_session(db, club_id, session_id)
    teams = session_teams(db, session_id)
    if not teams:
        raise Conflict("팀이 확정되지 않았습니다.", "SESSION_NOT_CONFIRMED")
    hist = _history(db, session_id)
    active = [m for m in hist if m.game_status in ACTIVE_STATUSES]
    played = [PlayedMatch(m.team_a_id, m.team_b_id) for m in hist]
    sug = match_order_strategy.suggest([t.session_team_id for t in teams], played)
    status = {x.team_id: x for x in sug.teams}
    next_no = (db.scalar(select(func.max(MatchGame.game_no)).where(MatchGame.session_id == session_id)) or 0) + 1
    return {
        "sessionId": s.session_id, "nextGameNo": next_no,
        "blockedByMatchId": active[0].match_id if active else None,
        "suggestedTeamAId": sug.team_a_id, "suggestedTeamBId": sug.team_b_id,
        "teams": [
            {"sessionTeamId": t.session_team_id, "teamCode": t.team_code, "displayName": t.display_name,
             "gamesPlayed": status[t.session_team_id].games, "consecutive": status[t.session_team_id].consecutive,
             "lastPlayedGameNo": hist[status[t.session_team_id].last_index].game_no
             if status[t.session_team_id].last_index >= 0 else None}
            for t in teams
        ],
    }


def create_next_match(db: Session, club_id: int, session_id: int, admin_id: int | None, *,
                      team_a_id: int | None, team_b_id: int | None, duration_sec: int | None = None) -> MatchGame:
    """다음 경기 생성. 대진(두 팀)은 관리자가 매번 지정한다."""
    s = get_session(db, club_id, session_id, lock=True)
    guard_not_closed(s)
    if s.status not in (SessionStatus.CONFIRMED, SessionStatus.IN_PROGRESS):
        raise Conflict("팀이 확정된 일정에서만 경기를 만들 수 있습니다.", "SESSION_NOT_CONFIRMED")
    team_ids = [t.session_team_id for t in session_teams(db, session_id)]
    hist = _history(db, session_id)
    if any(m.game_status in ACTIVE_STATUSES for m in hist):
        raise Conflict("대기/진행 중인 경기가 있습니다. 먼저 종료하거나 취소하세요.", "ACTIVE_MATCH_EXISTS")
    if team_a_id is None or team_b_id is None:
        raise BadRequest("맞붙을 두 팀을 선택하세요.", "TEAMS_REQUIRED")
    if team_a_id not in team_ids or team_b_id not in team_ids or team_a_id == team_b_id:
        raise BadRequest("대진 팀이 올바르지 않습니다.", "INVALID_TEAM")
    cfg = load_config(db, club_id)
    a, b = team_a_id, team_b_id

    early = int(cfg["MATCH_EARLY_END_GOALS"])
    # 취소된 경기도 번호는 유지하므로 전체 MAX 기준으로 증가
    next_no = (db.scalar(select(func.max(MatchGame.game_no)).where(MatchGame.session_id == session_id)) or 0) + 1
    if duration_sec is not None and duration_sec < 10:
        raise BadRequest("경기 시간은 10초 이상이어야 합니다.")
    m = MatchGame(
        session_id=session_id, game_no=next_no,
        team_a_id=a, team_b_id=b, score_a=0, score_b=0, game_status=GameStatus.READY,
        game_duration_sec=int(duration_sec or cfg["MATCH_DURATION_SEC"]), auto_end_yn=bool(cfg["MATCH_AUTO_END_YN"]),
        early_end_goals=early if early > 0 else None, paused_seconds=0.0, version=0,
    )
    db.add(m)
    db.flush()
    _emit_state(db, club_id, m)
    db.commit()
    return m


def live_matches(db: Session, club_id: int) -> list[dict]:
    """홈 LIVE 배너용: 열린 일정의 대기/진행/일시정지 경기."""
    rows = db.execute(
        select(MatchGame, ClubSession)
        .join(ClubSession, ClubSession.session_id == MatchGame.session_id)
        .where(ClubSession.club_id == club_id,
               ClubSession.status.in_([SessionStatus.CONFIRMED, SessionStatus.IN_PROGRESS]),
               MatchGame.game_status.in_(ACTIVE_STATUSES))
        .order_by(ClubSession.session_date, MatchGame.game_no)
    ).all()
    return [{**match_state(db, m), "sessionDate": s.session_date, "sessionTitle": s.title} for m, s in rows]


# ------------------------------------------------------------------ 진행
def _lock(db: Session, club_id: int, match_id: int) -> tuple[MatchGame, ClubSession]:
    m, s = get_match(db, club_id, match_id, lock=True)
    guard_not_closed(s)
    return m, s


def _require(m: MatchGame, *statuses: str) -> None:
    if m.game_status not in statuses:
        raise Conflict(f"현재 경기 상태({m.game_status})에서는 할 수 없는 작업입니다.", "INVALID_MATCH_STATUS")


def start_match(db: Session, club_id: int, match_id: int, admin_id: int | None) -> MatchGame:
    m, s = _lock(db, club_id, match_id)
    _require(m, GameStatus.READY)
    running = db.scalar(select(func.count()).select_from(MatchGame).where(
        MatchGame.session_id == m.session_id, MatchGame.match_id != m.match_id,
        MatchGame.game_status.in_([GameStatus.RUNNING, GameStatus.PAUSED])))
    if running:
        raise Conflict("이미 진행 중인 경기가 있습니다.", "ACTIVE_MATCH_EXISTS")

    # 출전 명단: 경기 시작 시점의 팀 명단(이후 결장/추가는 별도 수정)
    if not db.scalar(select(func.count()).select_from(MatchMember).where(MatchMember.match_id == m.match_id)):
        for stm in db.scalars(select(SessionTeamMember).where(
                SessionTeamMember.session_id == m.session_id, SessionTeamMember.active_yn.is_(True),
                SessionTeamMember.session_team_id.in_([m.team_a_id, m.team_b_id]))):
            db.add(MatchMember(match_id=m.match_id, member_id=stm.member_id, session_team_id=stm.session_team_id))
        db.flush()

    # 경기 시작 시점 전력 Snapshot(이변/접전 판단용)
    cfg = load_config(db, club_id)
    mms = list(db.scalars(select(MatchMember).where(MatchMember.match_id == m.match_id)))
    states = current_states(db, club_id, [x.member_id for x in mms], cfg)
    guests = {tid: db.scalar(select(func.count()).select_from(SessionGuest).where(
        SessionGuest.session_team_id == tid, SessionGuest.active_yn.is_(True))) or 0
        for tid in (m.team_a_id, m.team_b_id)}
    ra = [states[x.member_id].rating for x in mms if x.session_team_id == m.team_a_id]
    rb = [states[x.member_id].rating for x in mms if x.session_team_id == m.team_b_id]
    m.team_a_headcount = len(ra) + guests[m.team_a_id]
    m.team_b_headcount = len(rb) + guests[m.team_b_id]
    m.team_a_strength = team_strength_strategy.calculate_team_strength(ra, m.team_a_headcount, cfg)
    m.team_b_strength = team_strength_strategy.calculate_team_strength(rb, m.team_b_headcount, cfg)
    m.expected_a = expected_score(m.team_a_strength, m.team_b_strength, float(cfg["RATING_EXPECTATION_SCALE"]))

    m.started_at = utcnow()
    m.paused_seconds = 0.0
    m.game_status = GameStatus.RUNNING
    m.version += 1
    _event(db, m, EventType.START, admin_id, elapsed_sec=0, remaining_sec=m.game_duration_sec)
    if s.status == SessionStatus.CONFIRMED:
        s.status = SessionStatus.IN_PROGRESS
        emit(db, club_id, "SESSION_UPDATED", {"sessionId": s.session_id, "status": s.status})
    _emit_state(db, club_id, m)
    db.commit()
    return m


def pause_match(db: Session, club_id: int, match_id: int, admin_id: int | None) -> MatchGame:
    m, _ = _lock(db, club_id, match_id)
    _require(m, GameStatus.RUNNING)
    now = utcnow()
    el = elapsed_seconds(m, now)
    m.paused_at = now
    m.game_status = GameStatus.PAUSED
    m.version += 1
    _event(db, m, EventType.PAUSE, admin_id, elapsed_sec=int(el), remaining_sec=int(m.game_duration_sec - el))
    _emit_state(db, club_id, m)
    db.commit()
    return m


def resume_match(db: Session, club_id: int, match_id: int, admin_id: int | None) -> MatchGame:
    m, _ = _lock(db, club_id, match_id)
    _require(m, GameStatus.PAUSED)
    now = utcnow()
    m.paused_seconds = (m.paused_seconds or 0.0) + (now - m.paused_at).total_seconds()
    m.paused_at = None
    m.game_status = GameStatus.RUNNING
    m.version += 1
    el = elapsed_seconds(m, now)
    _event(db, m, EventType.RESUME, admin_id, elapsed_sec=int(el), remaining_sec=int(m.game_duration_sec - el))
    _emit_state(db, club_id, m)
    db.commit()
    return m


def _finish(db: Session, m: MatchGame, at: datetime, reason: EndReason, admin_id: int | None) -> None:
    if m.game_status == GameStatus.PAUSED and m.paused_at is not None:
        m.paused_seconds = (m.paused_seconds or 0.0) + max(0.0, (at - m.paused_at).total_seconds())
        m.paused_at = None
    m.finished_at = at
    m.game_status = GameStatus.FINISHED
    m.end_reason = reason
    m.version += 1
    el = elapsed_seconds(m)
    _event(db, m, EventType.END, admin_id, elapsed_sec=int(round(el)), remaining_sec=int(round(m.game_duration_sec - el)),
           memo=reason)


def end_match(db: Session, club_id: int, match_id: int, admin_id: int | None) -> MatchGame:
    m, _ = _lock(db, club_id, match_id)
    _require(m, GameStatus.RUNNING, GameStatus.PAUSED)
    _finish(db, m, utcnow(), EndReason.ADMIN, admin_id)
    _emit_state(db, club_id, m)
    db.commit()
    return m


def cancel_match(db: Session, club_id: int, match_id: int, admin_id: int | None) -> MatchGame:
    m, _ = _lock(db, club_id, match_id)
    if m.finalized_at:
        raise Conflict("확정된 경기는 취소할 수 없습니다. 먼저 확정을 해제하세요.", "MATCH_FINALIZED")
    _require(m, GameStatus.READY, GameStatus.RUNNING, GameStatus.PAUSED, GameStatus.FINISHED)
    m.game_status = GameStatus.CANCELLED
    m.version += 1
    _event(db, m, EventType.CANCEL, admin_id)
    _emit_state(db, club_id, m)
    db.commit()
    return m


def _deadline(m: MatchGame) -> datetime:
    return m.started_at + timedelta(seconds=(m.paused_seconds or 0.0) + m.game_duration_sec)


def check_time_up(db: Session, club_id: int, match_id: int) -> bool:
    """RUNNING인데 시간이 지났으면 자동 종료(AUTO_END_YN). 백그라운드 루프 + 조회 시 지연 처리 모두에서 사용."""
    m, s = get_match(db, club_id, match_id, lock=True)
    if m.game_status != GameStatus.RUNNING or not m.auto_end_yn or m.started_at is None:
        db.rollback()
        return False
    if utcnow() < _deadline(m):
        db.rollback()
        return False
    _finish(db, m, _deadline(m), EndReason.TIME_UP, None)
    _emit_state(db, club_id, m)
    db.commit()
    return True


def auto_end_due_matches() -> int:
    """백그라운드 타이머 루프에서 호출."""
    n = 0
    with SessionLocal() as db:
        rows = db.execute(
            select(MatchGame.match_id, ClubSession.club_id, MatchGame.started_at, MatchGame.paused_seconds,
                   MatchGame.game_duration_sec)
            .join(ClubSession, ClubSession.session_id == MatchGame.session_id)
            .where(MatchGame.game_status == GameStatus.RUNNING, MatchGame.auto_end_yn.is_(True))
        ).all()
        db.rollback()
        now = utcnow()
        for match_id, club_id, started, paused, dur in rows:
            if started and now >= started + timedelta(seconds=(paused or 0.0) + dur):
                if check_time_up(db, club_id, match_id):
                    n += 1
    return n


# ------------------------------------------------------------------ 골
def add_goal(db: Session, club_id: int, match_id: int, admin_id: int | None, *, team_id: int,
             scorer_member_id: int | None = None, assist_member_id: int | None = None, own_goal: bool = False,
             guest_goal: bool = False, elapsed_sec: int | None = None, idempotency_key: str | None = None,
             memo: str | None = None) -> tuple[MatchEvent, MatchGame, bool]:
    """반환: (이벤트, 경기, 새로 생성 여부). 같은 멱등키 재요청이면 기존 이벤트를 그대로 돌려준다."""
    m, s = _lock(db, club_id, match_id)
    if idempotency_key:
        dup = db.scalar(select(MatchEvent).where(MatchEvent.match_id == match_id,
                                                 MatchEvent.idempotency_key == idempotency_key))
        if dup:
            db.rollback()
            return dup, m, False
    if m.finalized_at:
        raise Conflict("확정된 경기는 수정할 수 없습니다. 확정을 해제한 뒤 수정하세요.", "MATCH_FINALIZED")
    _require(m, GameStatus.RUNNING, GameStatus.PAUSED, GameStatus.FINISHED)
    if team_id not in (m.team_a_id, m.team_b_id):
        raise BadRequest("득점 팀은 이 경기의 팀이어야 합니다.", "INVALID_TEAM")
    other = m.team_b_id if team_id == m.team_a_id else m.team_a_id
    roster = {mm.member_id: mm.session_team_id
              for mm in db.scalars(select(MatchMember).where(MatchMember.match_id == match_id))}

    def guests_on(tid: int) -> int:
        return db.scalar(select(func.count()).select_from(SessionGuest).where(
            SessionGuest.session_team_id == tid, SessionGuest.active_yn.is_(True))) or 0

    # 득점자/자책/게스트 검증
    if guest_goal:
        if scorer_member_id is not None:
            raise BadRequest("게스트 득점은 득점자 멤버를 지정하지 않습니다.")
        if guests_on(other if own_goal else team_id) == 0:
            raise BadRequest("해당 팀에 게스트가 없습니다.", "NO_GUEST")
    elif own_goal:
        if scorer_member_id is None or roster.get(scorer_member_id) != other:
            raise BadRequest("자책골은 상대 팀 출전 선수를 지정해야 합니다.", "INVALID_SCORER")
    else:
        if scorer_member_id is None or roster.get(scorer_member_id) != team_id:
            raise BadRequest("득점자는 득점 팀의 출전 선수여야 합니다.", "INVALID_SCORER")
    if assist_member_id is not None:
        if own_goal:
            raise BadRequest("자책골에는 도움을 기록하지 않습니다.")
        if roster.get(assist_member_id) != team_id:
            raise BadRequest("도움 선수는 득점 팀의 출전 선수여야 합니다.", "INVALID_ASSIST")
        if assist_member_id == scorer_member_id:
            raise BadRequest("득점자와 도움 선수가 같을 수 없습니다.", "INVALID_ASSIST")

    now = utcnow()
    current = elapsed_seconds(m, now)
    if elapsed_sec is not None:
        if elapsed_sec < 0 or elapsed_sec > math.ceil(current) + 1:
            raise BadRequest("득점 시각(elapsedSec)이 경기 진행 시간을 벗어났습니다.")
        el = int(elapsed_sec)
    else:
        el = int(current)

    e = MatchEvent(match_id=match_id, event_type=EventType.GOAL, team_id=team_id,
                   scorer_member_id=scorer_member_id, assist_member_id=assist_member_id,
                   own_goal_yn=own_goal, guest_goal_yn=guest_goal, elapsed_sec=el,
                   remaining_sec=m.game_duration_sec - el, idempotency_key=idempotency_key, memo=memo,
                   admin_id=admin_id)
    db.add(e)
    try:
        db.flush()
    except IntegrityError:
        db.rollback()  # 동시에 같은 멱등키가 들어온 경우
        dup = db.scalar(select(MatchEvent).where(MatchEvent.match_id == match_id,
                                                 MatchEvent.idempotency_key == idempotency_key))
        if dup:
            return dup, get_match(db, club_id, match_id)[0], False
        raise
    if team_id == m.team_a_id:
        m.score_a += 1
    else:
        m.score_b += 1
    m.version += 1

    if (m.early_end_goals and m.game_status in (GameStatus.RUNNING, GameStatus.PAUSED)
            and max(m.score_a, m.score_b) >= m.early_end_goals):
        _finish(db, m, now, EndReason.EARLY_GOAL, admin_id)

    names = member_names(db, [scorer_member_id, assist_member_id])
    emit(db, club_id, "MATCH_EVENT", {"matchId": m.match_id, "sessionId": m.session_id,
                                      "event": serialize_event(e, names)})
    _emit_state(db, club_id, m)
    db.commit()
    return e, m, True


def cancel_goal(db: Session, club_id: int, match_id: int, event_id: int, admin_id: int | None,
                memo: str | None = None) -> tuple[MatchEvent, MatchGame]:
    m, _ = _lock(db, club_id, match_id)
    if m.finalized_at:
        raise Conflict("확정된 경기는 수정할 수 없습니다. 확정을 해제한 뒤 수정하세요.", "MATCH_FINALIZED")
    ev = db.scalar(select(MatchEvent).where(MatchEvent.event_id == event_id, MatchEvent.match_id == match_id))
    if not ev or ev.event_type != EventType.GOAL:
        raise NotFound("골 이벤트를 찾을 수 없습니다.", "EVENT_NOT_FOUND")
    if ev.cancelled_yn:
        raise Conflict("이미 취소된 골입니다.", "ALREADY_CANCELLED")
    ev.cancelled_yn = True
    rev = _event(db, m, EventType.GOAL_CANCEL, admin_id, team_id=ev.team_id, ref_event_id=ev.event_id,
                 elapsed_sec=int(elapsed_seconds(m)), memo=memo)
    if ev.team_id == m.team_a_id:
        m.score_a = max(0, m.score_a - 1)
    else:
        m.score_b = max(0, m.score_b - 1)
    m.version += 1
    emit(db, club_id, "MATCH_EVENT", {"matchId": m.match_id, "sessionId": m.session_id,
                                      "event": serialize_event(rev, {})})
    _emit_state(db, club_id, m)
    db.commit()
    return rev, m


# ------------------------------------------------------------------ 출전 명단 수정
def _has_goal_events(db: Session, match_id: int, member_id: int) -> bool:
    return bool(db.scalar(select(func.count()).select_from(MatchEvent).where(
        MatchEvent.match_id == match_id, MatchEvent.event_type == EventType.GOAL, MatchEvent.cancelled_yn.is_(False),
        (MatchEvent.scorer_member_id == member_id) | (MatchEvent.assist_member_id == member_id))))


def add_match_member(db: Session, club_id: int, match_id: int, member_id: int, team_id: int,
                     admin_id: int | None) -> None:
    m, _ = _lock(db, club_id, match_id)
    if m.finalized_at:
        raise Conflict("확정된 경기는 수정할 수 없습니다.", "MATCH_FINALIZED")
    _require(m, GameStatus.RUNNING, GameStatus.PAUSED, GameStatus.FINISHED)
    if team_id not in (m.team_a_id, m.team_b_id):
        raise BadRequest("팀이 올바르지 않습니다.", "INVALID_TEAM")
    if not db.scalar(select(Member).where(Member.member_id == member_id, Member.club_id == club_id)):
        raise NotFound("멤버를 찾을 수 없습니다.", "MEMBER_NOT_FOUND")
    mm = db.scalar(select(MatchMember).where(MatchMember.match_id == match_id, MatchMember.member_id == member_id))
    if mm and mm.session_team_id != team_id and _has_goal_events(db, match_id, member_id):
        raise Conflict("골/도움 기록이 있는 선수는 팀을 바꿀 수 없습니다. 골을 먼저 취소하세요.", "MEMBER_HAS_EVENTS")
    if mm:
        mm.session_team_id = team_id
    else:
        db.add(MatchMember(match_id=match_id, member_id=member_id, session_team_id=team_id))
    _event(db, m, EventType.MEMBER_ADD, admin_id, team_id=team_id, member_id=member_id)
    m.version += 1
    _emit_state(db, club_id, m)
    db.commit()


def remove_match_member(db: Session, club_id: int, match_id: int, member_id: int, admin_id: int | None) -> None:
    m, _ = _lock(db, club_id, match_id)
    if m.finalized_at:
        raise Conflict("확정된 경기는 수정할 수 없습니다.", "MATCH_FINALIZED")
    mm = db.scalar(select(MatchMember).where(MatchMember.match_id == match_id, MatchMember.member_id == member_id))
    if not mm:
        raise NotFound("출전 명단에 없는 멤버입니다.", "NOT_IN_MATCH")
    if _has_goal_events(db, match_id, member_id):
        raise Conflict("골/도움 기록이 있는 선수는 출전 명단에서 뺄 수 없습니다. 골을 먼저 취소하세요.", "MEMBER_HAS_EVENTS")
    db.delete(mm)  # 출전 명단은 경기 확정 전 작업 데이터. 변경 이력은 MATCH_EVENT(MEMBER_REMOVE)로 남김
    _event(db, m, EventType.MEMBER_REMOVE, admin_id, team_id=mm.session_team_id, member_id=member_id)
    m.version += 1
    _emit_state(db, club_id, m)
    db.commit()


# ------------------------------------------------------------------ 확정(Finalize)
def _apply_finalize(db: Session, m: MatchGame, admin_id: int | None) -> None:
    m.win_team_id = winner_of(m)
    m.finalized_at = utcnow()
    m.version += 1
    _event(db, m, EventType.FINALIZE, admin_id, team_id=m.win_team_id)


def finalize_match(db: Session, club_id: int, match_id: int, admin_id: int | None) -> MatchGame:
    """기록 확정 → 승/무/패 확정, Rating/Stats/Pair 반영. 두 번 호출되면 409(멱등)."""
    m, s = _lock(db, club_id, match_id)
    if m.finalized_at:
        raise Conflict("이미 확정된 경기입니다.", "ALREADY_FINALIZED")
    _require(m, GameStatus.FINISHED)
    pending_before = db.scalar(select(func.count()).select_from(MatchGame).where(
        MatchGame.session_id == m.session_id, MatchGame.game_no < m.game_no,
        MatchGame.game_status != GameStatus.CANCELLED, MatchGame.finalized_at.is_(None)))
    if pending_before:
        raise Conflict("앞 번호 경기를 먼저 확정하세요(GAME_NO 순서).", "FINALIZE_ORDER")
    guard_after_closed(db, club_id, (s.session_date, s.session_id))
    _apply_finalize(db, m, admin_id)
    rebuild_ratings(db, club_id, match_key(s, m))
    rebuild_all_stats(db, club_id)
    _emit_state(db, club_id, m)
    db.commit()
    return m


def unfinalize_match(db: Session, club_id: int, match_id: int, admin_id: int | None) -> MatchGame:
    """확정 해제(일정 마감 전까지만). 해당 경기 이후 Rating은 무효화 후 재계산."""
    m, s = _lock(db, club_id, match_id)
    if not m.finalized_at:
        raise Conflict("확정되지 않은 경기입니다.", "NOT_FINALIZED")
    guard_after_closed(db, club_id, (s.session_date, s.session_id))
    m.finalized_at = None
    m.win_team_id = None
    m.version += 1
    _event(db, m, EventType.UNFINALIZE, admin_id)
    db.flush()
    rebuild_ratings(db, club_id, match_key(s, m))
    rebuild_all_stats(db, club_id)
    _emit_state(db, club_id, m)
    db.commit()
    return m


def finalize_remaining_for_close(db: Session, club_id: int, s: ClubSession, admin_id: int | None) -> int:
    """[일정마감] 시: READY 경기는 취소, FINISHED 미확정 경기는 순서대로 확정. 호출 측 트랜잭션."""
    ms = list(db.scalars(select(MatchGame).where(MatchGame.session_id == s.session_id)
                         .order_by(MatchGame.game_no).with_for_update()))
    if any(x.game_status in (GameStatus.RUNNING, GameStatus.PAUSED) for x in ms):
        raise Conflict("진행 중인 경기가 있습니다. 경기를 먼저 종료하세요.", "ACTIVE_MATCH_EXISTS")
    first_key = None
    for x in ms:
        if x.game_status == GameStatus.READY:
            x.game_status = GameStatus.CANCELLED
            x.version += 1
            _event(db, x, EventType.CANCEL, admin_id, memo=EndReason.SESSION_CLOSE)
        elif x.game_status == GameStatus.FINISHED and x.finalized_at is None:
            _apply_finalize(db, x, admin_id)
            first_key = first_key or match_key(s, x)
    db.flush()
    if first_key:
        rebuild_ratings(db, club_id, first_key)
    return sum(1 for x in ms if x.finalized_at is not None)
