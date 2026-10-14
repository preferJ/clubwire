"""경기 진행(LIVE). 쓰기는 관리자 모드만, 조회는 공개."""
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import admin_dep, club_dep
from app.core.database import get_db
from app.core.security import AdminPrincipal
from app.models import Club
from app.models.enums import GameStatus
from app.schemas.requests import EventCancelRequest, GoalRequest, MatchMemberRequest, NextMatchRequest
from app.services import match_service
from app.services.common import get_match
from app.services.match_service import match_detail, match_state

router = APIRouter(tags=["matches"])


@router.get("/sessions/{session_id}/matches/next-suggestion", summary="다음 경기 대진 화면용: 팀별 경기 수 + 추천 대진")
def next_suggestion(session_id: int, club: Club = Depends(club_dep), admin: AdminPrincipal = Depends(admin_dep),
                    db: Session = Depends(get_db)):
    return match_service.next_suggestion(db, club.club_id, session_id)


@router.post("/sessions/{session_id}/matches/next", status_code=201, summary="다음 경기 생성(READY). 두 팀은 관리자가 지정")
def create_next(session_id: int, body: NextMatchRequest, club: Club = Depends(club_dep),
                admin: AdminPrincipal = Depends(admin_dep), db: Session = Depends(get_db)):
    m = match_service.create_next_match(db, club.club_id, session_id, admin.admin_id, team_a_id=body.team_a_id,
                                        team_b_id=body.team_b_id, duration_sec=body.duration_sec)
    return match_state(db, m)


@router.get("/live", summary="진행/대기 중인 경기(공개, 홈 LIVE 배너용)")
def live_matches(club: Club = Depends(club_dep), db: Session = Depends(get_db)):
    return match_service.live_matches(db, club.club_id)


@router.get("/matches/{match_id}", summary="경기 상태 + 이벤트 타임라인(공개). 새 클라이언트는 이걸로 타이머 복원")
def get_match_detail(match_id: int, club: Club = Depends(club_dep), db: Session = Depends(get_db)):
    m, _ = get_match(db, club.club_id, match_id)
    if m.game_status == GameStatus.RUNNING and m.auto_end_yn:
        match_service.check_time_up(db, club.club_id, match_id)  # 시간 초과면 지연 자동 종료
        m, _ = get_match(db, club.club_id, match_id)
    return match_detail(db, m)


def _action(fn):
    def handler(match_id: int, club: Club = Depends(club_dep), admin: AdminPrincipal = Depends(admin_dep),
                db: Session = Depends(get_db)):
        m = fn(db, club.club_id, match_id, admin.admin_id)
        return match_state(db, m)
    return handler


router.add_api_route("/matches/{match_id}/start", _action(match_service.start_match), methods=["POST"],
                     summary="경기 시작(출전 명단/전력 Snapshot 생성)")
router.add_api_route("/matches/{match_id}/pause", _action(match_service.pause_match), methods=["POST"], summary="일시정지")
router.add_api_route("/matches/{match_id}/resume", _action(match_service.resume_match), methods=["POST"], summary="재개")
router.add_api_route("/matches/{match_id}/end", _action(match_service.end_match), methods=["POST"], summary="경기 종료(관리자)")
router.add_api_route("/matches/{match_id}/cancel", _action(match_service.cancel_match), methods=["POST"], summary="경기 취소")
router.add_api_route("/matches/{match_id}/finalize", _action(match_service.finalize_match), methods=["POST"],
                     summary="기록 확정 → Rating/Stats/Pair 반영(중복 호출 409)")
router.add_api_route("/matches/{match_id}/unfinalize", _action(match_service.unfinalize_match), methods=["POST"],
                     summary="확정 해제(일정마감 전까지)")


@router.post("/matches/{match_id}/goals", summary="골 등록(+점수 동시 반영, 멱등키 지원)")
def add_goal(match_id: int, body: GoalRequest, club: Club = Depends(club_dep),
             admin: AdminPrincipal = Depends(admin_dep), db: Session = Depends(get_db)):
    e, m, created = match_service.add_goal(
        db, club.club_id, match_id, admin.admin_id, team_id=body.team_id, scorer_member_id=body.scorer_member_id,
        assist_member_id=body.assist_member_id, own_goal=body.own_goal, guest_goal=body.guest_goal,
        elapsed_sec=body.elapsed_sec, idempotency_key=body.idempotency_key, memo=body.memo)
    m, _ = get_match(db, club.club_id, match_id)
    return {"eventId": e.event_id, "duplicate": not created, "match": match_state(db, m)}


@router.post("/matches/{match_id}/events/{event_id}/cancel", summary="골 취소(삭제하지 않고 취소 이벤트 기록)")
def cancel_goal(match_id: int, event_id: int, body: EventCancelRequest | None = None, club: Club = Depends(club_dep),
                admin: AdminPrincipal = Depends(admin_dep), db: Session = Depends(get_db)):
    rev, m = match_service.cancel_goal(db, club.club_id, match_id, event_id, admin.admin_id, body.memo if body else None)
    return {"eventId": rev.event_id, "match": match_state(db, m)}


@router.post("/matches/{match_id}/members", summary="출전 명단 추가/팀 변경(교체 투입 등)")
def add_match_member(match_id: int, body: MatchMemberRequest, club: Club = Depends(club_dep),
                     admin: AdminPrincipal = Depends(admin_dep), db: Session = Depends(get_db)):
    match_service.add_match_member(db, club.club_id, match_id, body.member_id, body.team_id, admin.admin_id)
    m, _ = get_match(db, club.club_id, match_id)
    return match_detail(db, m)


@router.delete("/matches/{match_id}/members/{member_id}", summary="출전 명단 제외(결장)")
def remove_match_member(match_id: int, member_id: int, club: Club = Depends(club_dep),
                        admin: AdminPrincipal = Depends(admin_dep), db: Session = Depends(get_db)):
    match_service.remove_match_member(db, club.club_id, match_id, member_id, admin.admin_id)
    m, _ = get_match(db, club.club_id, match_id)
    return match_detail(db, m)
