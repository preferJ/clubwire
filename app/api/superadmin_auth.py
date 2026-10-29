"""전체 관리자 로그인. 클럽 DB나 클럽 관리자 인증을 사용하지 않는다."""
from fastapi import APIRouter, Depends, Request

from app.core.superadmin import SuperAdminPrincipal, superadmin_dep, superadmin_login
from app.core.timeutil import to_iso
from app.schemas.requests import AdminAuthRequest

router = APIRouter(prefix="/api/admin", tags=["superadmin"])


@router.post("/auth", summary="전체 관리자 모드 진입(PIN 입력 → 토큰)")
def authenticate(body: AdminAuthRequest, request: Request):
    client = request.client.host if request.client else "unknown"
    token, expires = superadmin_login(body.password, client)
    return {"accessToken": token, "tokenType": "Bearer", "expiresAt": to_iso(expires.replace(tzinfo=None))}


@router.get("/me", summary="전체 관리자 모드 확인")
def me(admin: SuperAdminPrincipal = Depends(superadmin_dep)):
    return {"role": admin.role}
