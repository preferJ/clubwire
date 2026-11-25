"""서버 전용 카카오 OAuth와 사용자 세션, 기존 선수 연결 승인."""
import secrets
from datetime import datetime, timedelta, timezone
from urllib.parse import urlencode, urlsplit

import httpx
import jwt
from fastapi import Request
from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.errors import BadRequest, Conflict, Forbidden, NotFound, Unauthorized
from app.core.timeutil import to_iso, utcnow
from app.models import AppUser, Member, MemberAccountLink, MemberLinkRequest
from app.core.database import emit
from app.services.common import get_member, lock_club

USER_COOKIE = "clubwire_user"
STATE_COOKIE = "clubwire_kakao_state"
STATE_COOKIE_PATH = "/api/auth/kakao"
_ALGORITHM = "HS256"


def oauth_configured() -> bool:
    try:
        _redirect_uri()
    except BadRequest:
        return False
    return bool(settings.KAKAO_CLIENT_ID and settings.KAKAO_CLIENT_ID.strip())


def _redirect_uri() -> str:
    uri = (settings.KAKAO_REDIRECT_URI or "").strip()
    try:
        parsed = urlsplit(uri)
        hostname = parsed.hostname
    except ValueError:
        raise BadRequest("카카오 로그인 Redirect URI 설정을 확인해 주세요.", "KAKAO_NOT_CONFIGURED") from None
    local = hostname in ("localhost", "127.0.0.1", "::1")
    if (not hostname or parsed.username or parsed.password or parsed.query or parsed.fragment
            or "\\" in uri or parsed.path != "/api/auth/kakao/callback"
            or not (parsed.scheme == "https" or (parsed.scheme == "http" and local))):
        raise BadRequest("카카오 로그인 Redirect URI 설정을 확인해 주세요.", "KAKAO_NOT_CONFIGURED")
    return uri


def secure_cookie() -> bool:
    # 공개 운영 환경에서는 HTTPS만 허용. http는 localhost 개발 설정에 한정한다.
    return urlsplit(_redirect_uri()).scheme == "https"


def create_user_token(user: AppUser) -> tuple[str, str]:
    csrf = secrets.token_urlsafe(32)
    now = datetime.now(timezone.utc)
    token = jwt.encode({"sub": str(user.user_id), "role": "USER", "ver": user.token_version,
                        "csrf": csrf, "iat": now,
                        "exp": now + timedelta(minutes=settings.USER_TOKEN_TTL_MIN)},
                       settings.SECRET_KEY, algorithm=_ALGORITHM)
    return token, csrf


def _user_claims(request: Request) -> dict | None:
    token = request.cookies.get(USER_COOKIE)
    if not token:
        return None
    try:
        claims = jwt.decode(token, settings.SECRET_KEY, algorithms=[_ALGORITHM],
                            options={"require": ["sub", "role", "ver", "csrf", "exp"]})
        if (claims.get("role") != "USER" or not str(claims.get("sub", "")).isdigit()
                or type(claims.get("ver")) is not int or not isinstance(claims.get("csrf"), str)
                or len(claims["csrf"]) < 20):
            return None
        return claims
    except (jwt.PyJWTError, ValueError, TypeError):
        return None


def optional_user(request: Request, db: Session) -> AppUser | None:
    claims = _user_claims(request)
    if not claims:
        return None
    user = db.get(AppUser, int(claims["sub"]))
    if not user or not user.active_yn or user.token_version != claims["ver"]:
        return None
    return user


def require_user(request: Request, db: Session, *, csrf: bool = True) -> AppUser:
    user = optional_user(request, db)
    if user is None:
        raise Unauthorized("카카오 로그인이 필요합니다.", "USER_LOGIN_REQUIRED")
    if csrf:
        supplied = request.headers.get("X-CSRF-Token", "")
        expected = (_user_claims(request) or {}).get("csrf", "")
        if not supplied or not supplied.isascii() or not expected.isascii() or not secrets.compare_digest(supplied, expected):
            raise Forbidden("인증 정보를 새로 불러온 뒤 다시 시도해 주세요.", "CSRF_INVALID")
    return user


def approved_member(db: Session, club_id: int, user_id: int) -> Member | None:
    return db.scalar(select(Member).join(MemberAccountLink, MemberAccountLink.member_id == Member.member_id)
                     .where(MemberAccountLink.club_id == club_id, MemberAccountLink.user_id == user_id,
                            Member.club_id == club_id, Member.active_yn.is_(True), Member.deleted_at.is_(None)))


def auth_view(request: Request, db: Session) -> dict:
    user = optional_user(request, db)
    return {"configured": oauth_configured(),
            "user": {"userId": user.user_id, "nickname": user.nickname} if user else None,
            "csrfToken": (_user_claims(request) or {}).get("csrf") if user else None}


def oauth_start(club_slug: str) -> tuple[str, str]:
    if not oauth_configured():
        raise BadRequest("관리자가 카카오 로그인 설정을 완료해야 합니다.", "KAKAO_NOT_CONFIGURED")
    nonce = secrets.token_urlsafe(32)
    state_cookie = jwt.encode({"role": "KAKAO_STATE", "state": nonce, "club": club_slug,
                               "exp": datetime.now(timezone.utc) + timedelta(minutes=10)},
                              settings.SECRET_KEY, algorithm=_ALGORITHM)
    return ("https://kauth.kakao.com/oauth/authorize?" + urlencode({"client_id": settings.KAKAO_CLIENT_ID,
            "redirect_uri": _redirect_uri(), "response_type": "code", "state": nonce}), state_cookie)


def oauth_state(request: Request, state: str | None) -> str:
    cookie = request.cookies.get(STATE_COOKIE, "")
    try:
        data = jwt.decode(cookie, settings.SECRET_KEY, algorithms=[_ALGORITHM],
                          options={"require": ["role", "state", "club", "exp"]})
        if (data.get("role") != "KAKAO_STATE" or not state or not isinstance(data.get("state"), str)
                or not state.isascii() or not data["state"].isascii()
                or not secrets.compare_digest(state, data["state"])):
            raise ValueError
        slug = data.get("club")
        # 슬러그는 로그인 시작 시 실제 활성 클럽으로 확인했다. 외부 주소/경로는 state에 넣지 않는다.
        if not isinstance(slug, str) or not slug or any(c not in "abcdefghijklmnopqrstuvwxyz0123456789_-" for c in slug):
            raise ValueError
        return slug
    except (jwt.PyJWTError, TypeError, ValueError):
        raise Unauthorized("로그인 요청이 만료되었거나 올바르지 않습니다. 다시 로그인해 주세요.", "OAUTH_STATE_INVALID") from None


def exchange_kakao(code: str) -> tuple[str, str]:
    """외부 토큰은 이 함수 안에서만 사용하며 DB/브라우저에 저장하지 않는다."""
    if not oauth_configured():
        raise BadRequest("카카오 로그인 설정을 확인해 주세요.", "KAKAO_NOT_CONFIGURED")
    form = {"grant_type": "authorization_code", "client_id": settings.KAKAO_CLIENT_ID,
            "redirect_uri": _redirect_uri(), "code": code}
    if settings.KAKAO_CLIENT_SECRET:
        form["client_secret"] = settings.KAKAO_CLIENT_SECRET
    try:
        with httpx.Client(timeout=10, follow_redirects=False) as client:
            token_response = client.post("https://kauth.kakao.com/oauth/token", data=form)
            token_response.raise_for_status()
            token_data = token_response.json()
            access = token_data.get("access_token")
            if not isinstance(access, str) or not access:
                raise ValueError
            profile_response = client.get("https://kapi.kakao.com/v2/user/me",
                                          headers={"Authorization": f"Bearer {access}"})
            profile_response.raise_for_status()
            profile = profile_response.json()
        kid = profile.get("id")
        if type(kid) is not int or kid <= 0:
            raise ValueError
        nickname = (profile.get("properties") or {}).get("nickname")
        if not isinstance(nickname, str) or not nickname.strip():
            nickname = "카카오 회원"
        return str(kid), nickname.strip()[:100]
    except (httpx.HTTPError, ValueError, TypeError, AttributeError):
        raise Unauthorized("카카오 로그인에 실패했습니다. 잠시 후 다시 시도해 주세요.", "KAKAO_LOGIN_FAILED") from None


def upsert_user(db: Session, kakao_id: str, nickname: str) -> AppUser:
    user = db.scalar(select(AppUser).where(AppUser.kakao_id == kakao_id))
    if not user:
        try:
            with db.begin_nested():
                user = AppUser(kakao_id=kakao_id, nickname=nickname)
                db.add(user)
                db.flush()
        except IntegrityError:
            user = db.scalar(select(AppUser).where(AppUser.kakao_id == kakao_id).with_for_update())
    if user is None or not user.active_yn:
        raise Forbidden("사용할 수 없는 계정입니다.", "USER_DISABLED")
    user.nickname = nickname
    db.commit()
    return user


def logout(db: Session, user: AppUser) -> None:
    # 이미 복사된 앱 세션도 만료되도록 계정의 세션 버전을 올린다(다른 기기도 로그아웃).
    db.execute(update(AppUser).where(AppUser.user_id == user.user_id)
               .values(token_version=AppUser.token_version + 1))
    db.commit()


def _request_view(row: MemberLinkRequest, member: Member, user: AppUser | None = None) -> dict:
    return {"requestId": row.request_id, "memberId": row.member_id, "name": member.name,
            "status": row.status, "createdAt": to_iso(row.created_at),
            **({"userId": row.user_id, "nickname": user.nickname} if user else {})}


def account_view(request: Request, db: Session, club_id: int) -> dict:
    result = {**auth_view(request, db), "link": None, "request": None}
    if not result["user"]:
        return result
    uid = result["user"]["userId"]
    link = db.execute(select(MemberAccountLink, Member).join(Member, Member.member_id == MemberAccountLink.member_id)
                      .where(MemberAccountLink.club_id == club_id, MemberAccountLink.user_id == uid,
                             Member.club_id == club_id, Member.deleted_at.is_(None))).first()
    if link:
        result["link"] = {"memberId": link[1].member_id, "name": link[1].name}
    req = db.execute(select(MemberLinkRequest, Member).join(Member, Member.member_id == MemberLinkRequest.member_id)
                     .where(MemberLinkRequest.club_id == club_id, MemberLinkRequest.user_id == uid)
                     .order_by(MemberLinkRequest.request_id.desc()).limit(1)).first()
    if req:
        result["request"] = _request_view(*req)
    return result


def request_link(db: Session, club_id: int, user: AppUser, member_id: int) -> None:
    lock_club(db, club_id)  # 동일 계정의 중복 신청과 승인 경쟁을 직렬화한다.
    member = get_member(db, club_id, member_id)
    if member.deleted_at:
        raise NotFound("연결할 선수를 찾을 수 없습니다.", "MEMBER_NOT_FOUND")
    if db.scalar(select(MemberAccountLink.link_id).where(MemberAccountLink.club_id == club_id,
                                                         MemberAccountLink.user_id == user.user_id)):
        raise Conflict("이미 선수와 연결된 계정입니다. 운영진에게 연결 해제를 요청해 주세요.", "ACCOUNT_ALREADY_LINKED")
    if db.scalar(select(MemberAccountLink.link_id).where(MemberAccountLink.member_id == member_id)):
        raise Conflict("이미 다른 계정에 연결된 선수입니다.", "MEMBER_ALREADY_LINKED")
    pending = db.scalars(select(MemberLinkRequest).where(MemberLinkRequest.club_id == club_id,
                      MemberLinkRequest.user_id == user.user_id, MemberLinkRequest.status == "PENDING")).all()
    if any(r.member_id == member_id for r in pending):
        db.commit()
        return
    for r in pending:
        r.status, r.reviewed_at = "CANCELLED", utcnow()
    db.add(MemberLinkRequest(club_id=club_id, user_id=user.user_id, member_id=member_id))
    emit(db, club_id, "ACCOUNT_UPDATED", {})
    db.commit()


def cancel_request(db: Session, club_id: int, user: AppUser) -> None:
    lock_club(db, club_id)
    for row in db.scalars(select(MemberLinkRequest).where(MemberLinkRequest.club_id == club_id,
                          MemberLinkRequest.user_id == user.user_id, MemberLinkRequest.status == "PENDING")):
        row.status, row.reviewed_at = "CANCELLED", utcnow()
    emit(db, club_id, "ACCOUNT_UPDATED", {})
    db.commit()


def admin_accounts(db: Session, club_id: int) -> dict:
    pending = db.execute(select(MemberLinkRequest, Member, AppUser)
        .join(Member, Member.member_id == MemberLinkRequest.member_id)
        .join(AppUser, AppUser.user_id == MemberLinkRequest.user_id)
        .where(MemberLinkRequest.club_id == club_id, MemberLinkRequest.status == "PENDING")
        .order_by(MemberLinkRequest.request_id)).all()
    links = db.execute(select(MemberAccountLink, Member, AppUser)
        .join(Member, Member.member_id == MemberAccountLink.member_id)
        .join(AppUser, AppUser.user_id == MemberAccountLink.user_id)
        .where(MemberAccountLink.club_id == club_id).order_by(Member.name)).all()
    return {"requests": [_request_view(row, member, user) for row, member, user in pending],
            "links": [{"linkId": row.link_id, "userId": row.user_id, "nickname": user.nickname,
                       "memberId": member.member_id, "name": member.name, "approvedAt": to_iso(row.approved_at)}
                      for row, member, user in links]}


def review_request(db: Session, club_id: int, request_id: int, admin_id: int, approve: bool) -> None:
    lock_club(db, club_id)
    row = db.scalar(select(MemberLinkRequest).where(MemberLinkRequest.request_id == request_id,
                                                   MemberLinkRequest.club_id == club_id).with_for_update())
    if not row:
        raise NotFound("연결 신청을 찾을 수 없습니다.", "LINK_REQUEST_NOT_FOUND")
    if row.status != "PENDING":
        raise Conflict("이미 처리된 신청입니다.", "LINK_REQUEST_REVIEWED")
    if approve:
        member = get_member(db, club_id, row.member_id)
        user = db.get(AppUser, row.user_id)
        if member.deleted_at or not user or not user.active_yn:
            raise Conflict("삭제한 선수 또는 사용할 수 없는 계정은 연결할 수 없습니다.", "LINK_UNAVAILABLE")
        exists = db.scalar(select(MemberAccountLink.link_id).where(
            (MemberAccountLink.member_id == row.member_id)
            | ((MemberAccountLink.club_id == club_id) & (MemberAccountLink.user_id == row.user_id))))
        if exists:
            raise Conflict("이미 연결된 선수 또는 계정입니다.", "LINK_CONFLICT")
        db.add(MemberAccountLink(club_id=club_id, user_id=row.user_id, member_id=row.member_id,
                                 approved_by_admin_id=admin_id, approved_at=utcnow()))
        row.status = "APPROVED"
    else:
        row.status = "REJECTED"
    row.reviewed_by_admin_id, row.reviewed_at = admin_id, utcnow()
    emit(db, club_id, "ACCOUNT_UPDATED", {})
    db.commit()


def revoke_link(db: Session, club_id: int, link_id: int, admin_id: int) -> None:
    lock_club(db, club_id)
    link = db.scalar(select(MemberAccountLink).where(MemberAccountLink.link_id == link_id,
                                                    MemberAccountLink.club_id == club_id))
    if not link:
        raise NotFound("선수 연결을 찾을 수 없습니다.", "LINK_NOT_FOUND")
    for row in db.scalars(select(MemberLinkRequest).where(MemberLinkRequest.club_id == club_id,
                         MemberLinkRequest.user_id == link.user_id, MemberLinkRequest.status == "APPROVED")):
        row.status, row.reviewed_by_admin_id, row.reviewed_at = "REVOKED", admin_id, utcnow()
    db.delete(link)
    emit(db, club_id, "ACCOUNT_UPDATED", {})
    db.commit()
