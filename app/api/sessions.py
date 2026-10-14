"""일정 / 참석 / 게스트 / 팀 편성 / [일정확정] / [일정마감]."""
from datetime import date

from fastapi import APIRouter, BackgroundTasks, Depends, Query
from sqlalchemy.orm import Session

from app.api.deps import admin_dep, club_dep, optional_admin, schedule_articles
from app.core.database import get_db
from app.core.security import AdminPrincipal
from app.core.timeutil import to_iso
from app.models import Club
from app.schemas.requests import (
    AssignmentRequest,
    AttendeesAdd,
    GuestsAdd,
    SessionCreate,
    SessionUpdate,
    TeamConfirmRequest,
    TeamGenerateRequest,
)
from app.services import lifecycle_service, session_service, team_service
from app.services.common import get_session

router = APIRouter(prefix="/sessions", tags=["sessions"])


@router.get("", summary="일정 목록(공개)")
def list_sessions(limit: int = Query(30, le=100), before: date | None = None, club: Club = Depends(club_dep),
                  db: Session = Depends(get_db)):
    return [session_service.serialize_session(db, s) for s in session_service.list_sessions(db, club.club_id, limit, before)]


@router.post("", status_code=201, summary="일정 생성")
def create_session(body: SessionCreate, club: Club = Depends(club_dep), admin: AdminPrincipal = Depends(admin_dep),
                   db: Session = Depends(get_db)):
    s = session_service.create_session(db, club.club_id, body.session_date, body.title, body.location)
    return session_service.serialize_session(db, s, detail=True, admin=True)


@router.get("/{session_id}", summary="일정 상세(참석자/팀/경기) — 공개, 관리자는 Rating Snapshot 포함")
def get_session_detail(session_id: int, club: Club = Depends(club_dep),
                       admin: AdminPrincipal | None = Depends(optional_admin), db: Session = Depends(get_db)):
    s = get_session(db, club.club_id, session_id)
    return session_service.serialize_session(db, s, detail=True, admin=admin is not None)


@router.patch("/{session_id}", summary="일정 수정")
def update_session(session_id: int, body: SessionUpdate, club: Club = Depends(club_dep),
                   admin: AdminPrincipal = Depends(admin_dep), db: Session = Depends(get_db)):
    s = session_service.update_session(db, club.club_id, session_id, session_date=body.session_date,
                                       title=body.title, location=body.location)
    return session_service.serialize_session(db, s, detail=True, admin=True)


@router.post("/{session_id}/cancel", summary="일정 취소(경기 시작 전만)")
def cancel_session(session_id: int, club: Club = Depends(club_dep), admin: AdminPrincipal = Depends(admin_dep),
                   db: Session = Depends(get_db)):
    s = session_service.cancel_session(db, club.club_id, session_id)
    return session_service.serialize_session(db, s)


# ---------------------------------------------------------------- 참석/게스트 (팀 확정 전)
@router.post("/{session_id}/members", summary="참석자 등록")
def add_attendees(session_id: int, body: AttendeesAdd, club: Club = Depends(club_dep),
                  admin: AdminPrincipal = Depends(admin_dep), db: Session = Depends(get_db)):
    session_service.add_attendees(db, club.club_id, session_id, body.member_ids)
    return session_service.serialize_session(db, get_session(db, club.club_id, session_id), detail=True, admin=True)


@router.delete("/{session_id}/members/{member_id}", summary="참석 취소(ABSENT 처리)")
def remove_attendee(session_id: int, member_id: int, club: Club = Depends(club_dep),
                    admin: AdminPrincipal = Depends(admin_dep), db: Session = Depends(get_db)):
    session_service.remove_attendee(db, club.club_id, session_id, member_id)
    return {"ok": True}


@router.post("/{session_id}/guests", summary="게스트 추가(인원수에만 포함)")
def add_guests(session_id: int, body: GuestsAdd, club: Club = Depends(club_dep),
               admin: AdminPrincipal = Depends(admin_dep), db: Session = Depends(get_db)):
    gs = session_service.add_guests(db, club.club_id, session_id, body.count, body.names)
    return [{"guestId": g.guest_id, "name": g.guest_name} for g in gs]


@router.delete("/{session_id}/guests/{guest_id}", summary="게스트 제외")
def remove_guest(session_id: int, guest_id: int, club: Club = Depends(club_dep),
                 admin: AdminPrincipal = Depends(admin_dep), db: Session = Depends(get_db)):
    session_service.remove_guest(db, club.club_id, session_id, guest_id)
    return {"ok": True}


# ---------------------------------------------------------------- 팀
@router.post("/{session_id}/teams/generate", summary="자동 팀 편성 미리보기(여러 번 가능)")
def generate_teams(session_id: int, body: TeamGenerateRequest, club: Club = Depends(club_dep),
                   admin: AdminPrincipal = Depends(admin_dep), db: Session = Depends(get_db)):
    gen = team_service.generate_preview(db, club.club_id, session_id, body.team_count, body.seed)
    return team_service.serialize_generation(db, gen)


@router.post("/{session_id}/teams/confirm", summary="[일정확정] 팀 확정 → PRE_MATCH 기사 생성")
def confirm_teams(session_id: int, body: TeamConfirmRequest, background: BackgroundTasks,
                  club: Club = Depends(club_dep), admin: AdminPrincipal = Depends(admin_dep),
                  db: Session = Depends(get_db)):
    s, article_ids = lifecycle_service.confirm_session(db, club.club_id, session_id, body.generation_id, admin.admin_id)
    schedule_articles(background, article_ids)
    data = session_service.serialize_session(db, s, detail=True, admin=True)
    data["articleIds"] = article_ids
    return data


@router.get("/{session_id}/teams", summary="세션 팀 명단(공개)")
def get_teams(session_id: int, club: Club = Depends(club_dep), admin: AdminPrincipal | None = Depends(optional_admin),
              db: Session = Depends(get_db)):
    data = session_service.serialize_session(db, get_session(db, club.club_id, session_id), detail=True,
                                             admin=admin is not None)
    return {"sessionId": session_id, "teams": data["teams"], "balanceLabel": data["balanceLabel"]}


@router.post("/{session_id}/teams/assignments", summary="확정 후 수동 변경(ADD 지각/MOVE 이동/REMOVE 제외)")
def change_assignment(session_id: int, body: AssignmentRequest, club: Club = Depends(club_dep),
                      admin: AdminPrincipal = Depends(admin_dep), db: Session = Depends(get_db)):
    team_service.change_assignment(db, club.club_id, session_id, admin.admin_id, action=body.action,
                                   member_id=body.member_id, guest_id=body.guest_id, guest_name=body.guest_name,
                                   to_team_id=body.to_team_id, reason=body.reason)
    return session_service.serialize_session(db, get_session(db, club.club_id, session_id), detail=True, admin=True)


@router.get("/{session_id}/teams/assignments", summary="수동 변경 이력")
def assignment_logs(session_id: int, club: Club = Depends(club_dep), admin: AdminPrincipal = Depends(admin_dep),
                    db: Session = Depends(get_db)):
    return [{"logId": x.log_id, "action": x.action, "memberId": x.member_id, "guestId": x.guest_id,
             "fromTeamId": x.from_team_id, "toTeamId": x.to_team_id, "reason": x.reason,
             "createdAt": to_iso(x.created_at)} for x in team_service.assignment_logs(db, club.club_id, session_id)]


@router.get("/{session_id}/summary", summary="오늘 기록 요약(팀 성적, 득점/도움 상위, 미확정 경기 수)")
def session_summary(session_id: int, club: Club = Depends(club_dep), db: Session = Depends(get_db)):
    return session_service.session_summary(db, club.club_id, session_id)


# ---------------------------------------------------------------- 마감
@router.post("/{session_id}/close", summary="[일정마감] 수정 잠금 → 자동 타이틀/통계/마감 기사")
def close_session(session_id: int, background: BackgroundTasks, club: Club = Depends(club_dep),
                  admin: AdminPrincipal = Depends(admin_dep), db: Session = Depends(get_db)):
    s, article_ids = lifecycle_service.close_session(db, club.club_id, session_id, admin.admin_id)
    schedule_articles(background, article_ids)
    data = session_service.serialize_session(db, s, detail=True, admin=True)
    data["articleIds"] = article_ids
    return data
