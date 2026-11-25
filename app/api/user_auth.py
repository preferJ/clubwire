"""카카오 로그인은 전역, 선수 연결은 클럽별 관리자 승인으로 처리한다."""
from fastapi import APIRouter, Depends, Query, Request, Response
from fastapi.responses import JSONResponse, RedirectResponse
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from app.api.deps import admin_dep, club_dep
from app.core.database import get_db
from app.core.errors import DomainError
from app.core.security import AdminPrincipal
from app.models import Club
from app.services import user_auth_service as auth
from app.services.common import get_club_by_slug

router = APIRouter(prefix="/api/auth", tags=["user-auth"])
club_router = APIRouter(tags=["member-accounts"])


class LinkRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    member_id: int = Field(alias="memberId", strict=True, gt=0)


def private_response(response: Response) -> Response:
    response.headers["Cache-Control"] = "no-store"
    response.headers["Referrer-Policy"] = "no-referrer"
    return response


def clear_state(response: Response) -> None:
    response.delete_cookie(auth.STATE_COOKIE, path=auth.STATE_COOKIE_PATH, httponly=True, samesite="lax")


@router.get("/kakao/login")
def kakao_login(club_slug: str = Query(..., alias="clubSlug", min_length=1, max_length=50),
                db: Session = Depends(get_db)):
    club = get_club_by_slug(db, club_slug)
    url, state_cookie = auth.oauth_start(club.club_slug)
    response = RedirectResponse(url, status_code=302)
    response.set_cookie(auth.STATE_COOKIE, state_cookie, max_age=600, httponly=True,
                        secure=auth.secure_cookie(), samesite="lax", path=auth.STATE_COOKIE_PATH)
    return private_response(response)


@router.get("/kakao/callback")
def kakao_callback(request: Request, code: str | None = Query(None, max_length=4096),
                   state: str | None = Query(None, max_length=1024),
                   error: str | None = Query(None, max_length=200), db: Session = Depends(get_db)):
    # 인증 코드는 URL에 도착하지만 이후 응답·리다이렉트·일반 ASGI access log에는 남기지 않는다.
    request.scope["query_string"] = b""
    try:
        slug = auth.oauth_state(request, state)
    except DomainError:
        response = RedirectResponse("/?login=failed", status_code=303)
        clear_state(response)
        return private_response(response)
    path = f"/c/{slug}/account"
    try:
        get_club_by_slug(db, slug)  # 로그인 왕복 중 접근 중지된 클럽도 다시 검사
        if error or not code:
            response = RedirectResponse(f"{path}?login=failed", status_code=303)
        else:
            kakao_id, nickname = auth.exchange_kakao(code)
            user = auth.upsert_user(db, kakao_id, nickname)
            token, _ = auth.create_user_token(user)
            response = RedirectResponse(f"{path}?login=success", status_code=303)
            response.set_cookie(auth.USER_COOKIE, token, max_age=auth.settings.USER_TOKEN_TTL_MIN * 60,
                                httponly=True, secure=auth.secure_cookie(), samesite="lax", path="/")
    except DomainError:
        db.rollback()
        response = RedirectResponse(f"{path}?login=failed", status_code=303)
    clear_state(response)
    return private_response(response)


@router.get("/me")
def me(request: Request, db: Session = Depends(get_db)):
    return private_response(JSONResponse(auth.auth_view(request, db)))


@router.post("/logout")
def logout(request: Request, db: Session = Depends(get_db)):
    user = auth.require_user(request, db)
    auth.logout(db, user)
    response = JSONResponse({"ok": True})
    response.delete_cookie(auth.USER_COOKIE, path="/", httponly=True, samesite="lax")
    return private_response(response)


@club_router.get("/account")
def account(request: Request, club: Club = Depends(club_dep), db: Session = Depends(get_db)):
    return private_response(JSONResponse(auth.account_view(request, db, club.club_id)))


@club_router.post("/account/link")
def request_link(body: LinkRequest, request: Request, club: Club = Depends(club_dep), db: Session = Depends(get_db)):
    user = auth.require_user(request, db)
    auth.request_link(db, club.club_id, user, body.member_id)
    return private_response(JSONResponse(auth.account_view(request, db, club.club_id)))


@club_router.delete("/account/link")
def cancel_link_request(request: Request, club: Club = Depends(club_dep), db: Session = Depends(get_db)):
    user = auth.require_user(request, db)
    auth.cancel_request(db, club.club_id, user)
    return private_response(JSONResponse(auth.account_view(request, db, club.club_id)))


@club_router.get("/admin/accounts")
def admin_accounts(club: Club = Depends(club_dep), admin: AdminPrincipal = Depends(admin_dep),
                   db: Session = Depends(get_db)):
    return private_response(JSONResponse(auth.admin_accounts(db, club.club_id)))


@club_router.post("/admin/accounts/{request_id}/approve")
def approve(request_id: int, club: Club = Depends(club_dep), admin: AdminPrincipal = Depends(admin_dep),
            db: Session = Depends(get_db)):
    auth.review_request(db, club.club_id, request_id, admin.admin_id, True)
    return {"ok": True}


@club_router.post("/admin/accounts/{request_id}/reject")
def reject(request_id: int, club: Club = Depends(club_dep), admin: AdminPrincipal = Depends(admin_dep),
           db: Session = Depends(get_db)):
    auth.review_request(db, club.club_id, request_id, admin.admin_id, False)
    return {"ok": True}


@club_router.delete("/admin/accounts/{link_id}")
def revoke(link_id: int, club: Club = Depends(club_dep), admin: AdminPrincipal = Depends(admin_dep),
           db: Session = Depends(get_db)):
    auth.revoke_link(db, club.club_id, link_id, admin.admin_id)
    return {"ok": True}
