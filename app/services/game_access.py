"""경기 조작 권한: 클럽 관리자 또는 계정 연결이 승인된 일정 참석자."""
from fastapi import Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import Forbidden
from app.core.security import AdminPrincipal
from app.models import Club, SessionMember
from app.services.common import get_match, get_session
from app.services.user_auth_service import approved_member, optional_user, require_user


def _attending(db: Session, session_id: int, member_id: int) -> bool:
    return db.scalar(select(SessionMember.session_member_id).where(
        SessionMember.session_id == session_id, SessionMember.member_id == member_id,
        SessionMember.attendance_status == 'ATTENDING')) is not None


def session_access(db: Session, club: Club, session_id: int, request: Request,
                   admin: AdminPrincipal | None) -> dict:
    s = get_session(db, club.club_id, session_id)
    reason = None
    if s.deleted_at or s.status in ('CLOSED', 'CANCELLED'):
        reason = 'SESSION_CLOSED'
    elif admin is None:
        user = optional_user(request, db)
        if user is None:
            reason = 'LOGIN_REQUIRED'
        else:
            member = approved_member(db, club.club_id, user.user_id)
            if member is None:
                reason = 'LINK_REQUIRED'
            elif not _attending(db, session_id, member.member_id):
                reason = 'ATTENDANCE_REQUIRED'
    return {'sessionId': session_id, 'canControl': reason is None, 'reason': reason}


def authorize_game_control(db: Session, club: Club, request: Request, admin: AdminPrincipal | None,
                           *, session_id: int | None = None, match_id: int | None = None) -> None:
    if admin is not None:
        return
    user = require_user(request, db, csrf=request.method not in ('GET', 'HEAD', 'OPTIONS'))
    if match_id is not None:
        _, session = get_match(db, club.club_id, match_id)
        session_id = session.session_id
    else:
        get_session(db, club.club_id, session_id)
    member = approved_member(db, club.club_id, user.user_id)
    if member is None:
        raise Forbidden('관리자에게 선수 계정 연결을 승인받아 주세요.', 'MEMBER_LINK_REQUIRED')
    if not _attending(db, session_id, member.member_id):
        raise Forbidden('해당 일정의 참석자만 경기를 조작할 수 있어요.', 'ATTENDANCE_REQUIRED')
    db.info['actor_user_id'] = user.user_id
