"""자동 팀 편성(미리보기/확정 적용) + 확정 후 수동 변경."""
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.database import emit
from app.core.errors import BadRequest, Conflict, NotFound
from app.core.timeutil import utcnow
from app.models import (
    ClubSession,
    SessionGuest,
    SessionMember,
    SessionTeam,
    SessionTeamMember,
    TeamAssignmentLog,
    TeamGeneration,
)
from app.models.enums import AssignmentAction, AssignType, AttendanceStatus, GenerationStatus, SessionStatus
from app.services.common import get_member, get_session, guard_not_closed, member_names, session_teams
from app.services.config_service import load_config
from app.services.rating_service import confidence_of, current_states
from app.services.session_service import active_guests, attending_member_ids
from app.services.stats_service import pair_get, pair_map
from app.strategies.team_generation import MemberInput, balance_label, team_generator


def generate_preview(db: Session, club_id: int, session_id: int, team_count: int, seed: int | None = None) -> TeamGeneration:
    s = get_session(db, club_id, session_id, lock=True)
    guard_not_closed(s)
    if s.status != SessionStatus.OPEN:
        raise Conflict("이미 팀이 확정된 일정입니다. 확정 후에는 수동 변경을 사용하세요.", "SESSION_CONFIRMED")
    if team_count < 2 or team_count > 6:
        raise BadRequest("팀 수는 2~6 사이여야 합니다.")
    member_ids = attending_member_ids(db, session_id)
    guests = active_guests(db, session_id)
    if len(member_ids) + len(guests) < team_count * 2:
        raise BadRequest("팀당 최소 2명 이상이 되도록 참석자를 등록하세요.", "NOT_ENOUGH_PLAYERS")

    cfg = load_config(db, club_id)
    states = current_states(db, club_id, member_ids, cfg)
    inputs = [MemberInput(mid, states[mid].rating, confidence_of(states[mid], s.session_date, cfg)) for mid in member_ids]
    pairs = pair_map(db, club_id)

    def lookup(a: int, b: int) -> tuple[int, int]:
        p = pair_get(pairs, a, b)
        return (p.same_team_count, p.co_attendance_count) if p else (0, 0)

    result = team_generator.generate(inputs, [g.guest_id for g in guests], team_count, lookup, cfg, seed=seed)
    gen = TeamGeneration(
        session_id=session_id, status=GenerationStatus.PREVIEW, team_count=team_count,
        attendee_count=len(member_ids), guest_count=len(guests),
        algorithm_version=result.algorithm_version, config_version=cfg.version, config_snapshot_json=cfg.snapshot(),
        random_seed=result.seed, candidate_count=result.candidate_count,
        valid_candidate_count=result.valid_candidate_count, tolerance_fallback_yn=result.tolerance_fallback,
        spread_percent=result.spread_percent, pair_penalty=result.pair_penalty,
        result_json={
            "attendeeMemberIds": sorted(member_ids),
            "guestIds": sorted(g.guest_id for g in guests),
            "inputs": [{"memberId": i.member_id, "rating": i.rating, "confidence": i.confidence} for i in inputs],
            "teams": [
                {"teamCode": t.team_code, "memberIds": t.member_ids, "guestIds": t.guest_ids,
                 "avgRating": t.avg_rating, "strength": t.strength, "headcount": t.headcount,
                 "pairPenalty": t.pair_penalty}
                for t in result.teams
            ],
            **result.extra,
        },
    )
    db.add(gen)
    db.commit()
    return gen


def serialize_generation(db: Session, gen: TeamGeneration) -> dict:
    rj = gen.result_json
    ids = [mid for t in rj["teams"] for mid in t["memberIds"]]
    names = member_names(db, ids)
    inputs = {i["memberId"]: i for i in rj.get("inputs", [])}
    guest_names = {g.guest_id: g.guest_name for g in db.scalars(select(SessionGuest).where(SessionGuest.session_id == gen.session_id))}
    return {
        "generationId": gen.generation_id, "sessionId": gen.session_id, "status": gen.status,
        "teamCount": gen.team_count, "algorithmVersion": gen.algorithm_version, "configVersion": gen.config_version,
        "seed": gen.random_seed, "candidateCount": gen.candidate_count, "validCandidateCount": gen.valid_candidate_count,
        "toleranceFallback": gen.tolerance_fallback_yn, "spreadPercent": round(gen.spread_percent, 4),
        "pairPenalty": round(gen.pair_penalty, 4), "balanceLabel": balance_label(gen.spread_percent),
        "teams": [
            {
                "teamCode": t["teamCode"], "headcount": t["headcount"], "avgRating": round(t["avgRating"], 2),
                "strength": round(t["strength"], 2), "pairPenalty": round(t["pairPenalty"], 4),
                "members": [{"memberId": mid, "name": names.get(mid),
                             "rating": round(inputs.get(mid, {}).get("rating", 0), 2)} for mid in t["memberIds"]],
                "guests": [{"guestId": gid, "name": guest_names.get(gid)} for gid in t["guestIds"]],
            }
            for t in rj["teams"]
        ],
    }


def apply_generation(db: Session, s: ClubSession, generation_id: int) -> list[SessionTeam]:
    """[일정확정]의 팀 저장 부분. 호출 측 트랜잭션 안에서 실행."""
    gen = db.scalar(select(TeamGeneration).where(TeamGeneration.generation_id == generation_id,
                                                 TeamGeneration.session_id == s.session_id).with_for_update())
    if not gen:
        raise NotFound("팀 편성 결과를 찾을 수 없습니다.", "GENERATION_NOT_FOUND")
    if gen.status != GenerationStatus.PREVIEW:
        raise Conflict("이미 확정되었거나 폐기된 편성입니다.", "GENERATION_NOT_PREVIEW")
    rj = gen.result_json
    now_members = attending_member_ids(db, s.session_id)
    now_guests = sorted(g.guest_id for g in active_guests(db, s.session_id))
    if sorted(now_members) != rj["attendeeMemberIds"] or now_guests != rj["guestIds"]:
        raise Conflict("편성 이후 참석자가 바뀌었습니다. 팀을 다시 생성하세요.", "ATTENDEES_CHANGED")

    inputs = {i["memberId"]: i for i in rj["inputs"]}
    teams: list[SessionTeam] = []
    for order, t in enumerate(rj["teams"]):
        team = SessionTeam(
            session_id=s.session_id, generation_id=gen.generation_id, team_code=t["teamCode"],
            display_name=f"TEAM {t['teamCode']}", display_order=order,
            avg_rating_snapshot=t["avgRating"], team_strength_snapshot=t["strength"], headcount_snapshot=t["headcount"],
        )
        db.add(team)
        db.flush()
        teams.append(team)
        for mid in t["memberIds"]:
            db.add(SessionTeamMember(
                session_id=s.session_id, session_team_id=team.session_team_id, member_id=mid,
                rating_snapshot=inputs[mid]["rating"], confidence_snapshot=inputs[mid]["confidence"],
                assign_type=AssignType.AUTO,
            ))
        for gid in t["guestIds"]:
            g = db.get(SessionGuest, gid)
            g.session_team_id = team.session_team_id

    now = utcnow()
    gen.status = GenerationStatus.CONFIRMED
    gen.confirmed_at = now
    for other in db.scalars(select(TeamGeneration).where(TeamGeneration.session_id == s.session_id,
                                                         TeamGeneration.status == GenerationStatus.PREVIEW,
                                                         TeamGeneration.generation_id != gen.generation_id)):
        other.status = GenerationStatus.DISCARDED
    s.team_count = gen.team_count
    s.status = SessionStatus.CONFIRMED
    s.confirmed_at = now
    db.flush()
    return teams


# ------------------------------------------------------------------ 확정 후 수동 변경
def change_assignment(db: Session, club_id: int, session_id: int, admin_id: int | None, *, action: str,
                      member_id: int | None = None, guest_id: int | None = None, guest_name: str | None = None,
                      to_team_id: int | None = None, reason: str | None = None) -> TeamAssignmentLog:
    """지각 추가(ADD) / 팀 이동(MOVE) / 제외(REMOVE). 다음에 시작하는 경기부터 반영된다."""
    s = get_session(db, club_id, session_id, lock=True)
    guard_not_closed(s)
    if s.status not in (SessionStatus.CONFIRMED, SessionStatus.IN_PROGRESS):
        raise Conflict("팀이 확정된 일정에서만 수동 변경할 수 있습니다.", "SESSION_NOT_CONFIRMED")
    try:
        act = AssignmentAction(action)
    except ValueError as e:
        raise BadRequest("action은 ADD/MOVE/REMOVE 중 하나입니다.") from e
    team_ids = {t.session_team_id for t in session_teams(db, session_id)}
    if act in (AssignmentAction.ADD, AssignmentAction.MOVE) and to_team_id not in team_ids:
        raise BadRequest("이동/추가할 팀이 올바르지 않습니다.", "INVALID_TEAM")

    from_team: int | None = None
    if member_id is not None:
        member = get_member(db, club_id, member_id, active_only=(act == AssignmentAction.ADD))
        stm = db.scalar(select(SessionTeamMember).where(SessionTeamMember.session_id == session_id,
                                                        SessionTeamMember.member_id == member_id))
        if act == AssignmentAction.ADD:
            if stm and stm.active_yn:
                raise Conflict("이미 팀에 배정된 멤버입니다. MOVE를 사용하세요.", "ALREADY_ASSIGNED")
            sm = db.scalar(select(SessionMember).where(SessionMember.session_id == session_id,
                                                       SessionMember.member_id == member_id))
            if sm:
                sm.attendance_status = AttendanceStatus.ATTENDING
            else:
                db.add(SessionMember(session_id=session_id, member_id=member_id,
                                     attendance_status=AttendanceStatus.ATTENDING))
            cfg = load_config(db, club_id)
            st = current_states(db, club_id, [member_id], cfg)[member_id]
            conf = confidence_of(st, s.session_date, cfg)
            if stm:  # 제외됐던 멤버 재합류 → 같은 행 재활성화(UNIQUE SESSION_ID+MEMBER_ID)
                stm.session_team_id, stm.active_yn, stm.assign_type = to_team_id, True, AssignType.MANUAL
                stm.rating_snapshot, stm.confidence_snapshot = st.rating, conf
            else:
                db.add(SessionTeamMember(session_id=session_id, session_team_id=to_team_id, member_id=member.member_id,
                                         rating_snapshot=st.rating, confidence_snapshot=conf,
                                         assign_type=AssignType.MANUAL))
        else:
            if not stm or not stm.active_yn:
                raise NotFound("팀에 배정되지 않은 멤버입니다.", "NOT_ASSIGNED")
            from_team = stm.session_team_id
            if act == AssignmentAction.MOVE:
                if stm.session_team_id == to_team_id:
                    raise BadRequest("이미 해당 팀입니다.")
                stm.session_team_id = to_team_id
                stm.assign_type = AssignType.MANUAL
            else:
                stm.active_yn = False
                sm = db.scalar(select(SessionMember).where(SessionMember.session_id == session_id,
                                                           SessionMember.member_id == member_id))
                if sm:
                    sm.attendance_status = AttendanceStatus.ABSENT  # 이미 뛴 경기 기록(MATCH_MEMBER)은 유지
    else:
        if act == AssignmentAction.ADD:
            if guest_id is not None:
                raise BadRequest("게스트 추가는 guestName(선택)만 보내세요.")
            cnt = len(list(db.scalars(select(SessionGuest.guest_id).where(SessionGuest.session_id == session_id))))
            g = SessionGuest(session_id=session_id, guest_name=(guest_name or f"게스트{cnt + 1}").strip(),
                             session_team_id=to_team_id)
            db.add(g)
            db.flush()
            guest_id = g.guest_id
        else:
            g = db.scalar(select(SessionGuest).where(SessionGuest.guest_id == guest_id,
                                                     SessionGuest.session_id == session_id))
            if not g or not g.active_yn:
                raise NotFound("게스트를 찾을 수 없습니다.", "GUEST_NOT_FOUND")
            from_team = g.session_team_id
            if act == AssignmentAction.MOVE:
                g.session_team_id = to_team_id
            else:
                g.active_yn = False
        if guest_id is None:
            raise BadRequest("memberId 또는 guestId가 필요합니다.")

    log = TeamAssignmentLog(session_id=session_id, action=act, member_id=member_id, guest_id=guest_id,
                            from_team_id=from_team, to_team_id=to_team_id if act != AssignmentAction.REMOVE else None,
                            reason=reason, admin_id=admin_id)
    db.add(log)
    db.flush()
    emit(db, club_id, "TEAMS_UPDATED", {"sessionId": session_id})
    db.commit()
    return log


def assignment_logs(db: Session, club_id: int, session_id: int) -> list[TeamAssignmentLog]:
    get_session(db, club_id, session_id)
    return list(db.scalars(select(TeamAssignmentLog).where(TeamAssignmentLog.session_id == session_id)
                           .order_by(TeamAssignmentLog.log_id)))
