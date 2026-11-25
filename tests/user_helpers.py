"""앱 로그인 쿠키를 요청별로 전달하는 테스트 도우미(공유 TestClient 쿠키를 변경하지 않는다)."""
from dataclasses import dataclass
from uuid import uuid4

from sqlalchemy import select

from app.core.database import SessionLocal
from app.core.timeutil import utcnow
from app.models import Club, ClubAdmin, Member
from app.models.user import AppUser, MemberAccountLink, MemberLinkRequest
from app.services.user_auth_service import USER_COOKIE, create_user_token


@dataclass
class UserSession:
    user_id: int
    token: str
    csrf: str

    @property
    def headers(self) -> dict[str, str]:
        return {"Cookie": f"{USER_COOKIE}={self.token}", "X-CSRF-Token": self.csrf}


def make_user_session(api, member_id: int | None = None, *, pending: bool = False) -> UserSession:
    """member_id를 주면 승인 연결(또는 pending 신청), 생략하면 미연결 카카오 계정."""
    with SessionLocal() as db:
        club = db.scalar(select(Club).where(Club.club_slug == api.slug))
        user = AppUser(kakao_id=f"test-{uuid4().hex}", nickname="테스트 회원")
        db.add(user)
        db.flush()
        if member_id is not None:
            member = db.get(Member, member_id)
            assert member and member.club_id == club.club_id
            if pending:
                db.add(MemberLinkRequest(club_id=club.club_id, user_id=user.user_id,
                                         member_id=member_id, status="PENDING"))
            else:
                admin = db.scalar(select(ClubAdmin).where(ClubAdmin.club_id == club.club_id))
                db.add(MemberAccountLink(club_id=club.club_id, user_id=user.user_id, member_id=member_id,
                                         approved_by_admin_id=admin.admin_id, approved_at=utcnow()))
        db.commit()
        token, csrf = create_user_token(user)
        return UserSession(user.user_id, token, csrf)


def authenticate_member(api, member_id: int) -> UserSession:
    """해당 Api 인스턴스의 admin=False 요청만 회원 세션으로 보낸다."""
    session = make_user_session(api, member_id)
    original_headers = api._h
    api._h = lambda admin: original_headers(True) if admin else session.headers
    api.user_session = session
    return session
