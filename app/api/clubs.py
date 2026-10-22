"""클럽 정보 / 관리자 모드 / 운영 설정."""
from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from app.api.deps import admin_dep, club_dep, optional_admin
from app.core.database import get_db
from app.core.security import AdminPrincipal
from app.core.timeutil import local_today, to_iso
from app.models import Club
from app.schemas.requests import AdminAuthRequest, ChangePinRequest, ConfigUpdateRequest
from app.services import club_service, config_service

router = APIRouter(tags=["clubs"])


@router.get("", summary="클럽 정보(공개)")
def get_club(club: Club = Depends(club_dep), admin: AdminPrincipal | None = Depends(optional_admin)):
    return {"clubId": club.club_id, "clubSlug": club.club_slug, "clubName": club.club_name,
            "sportType": club.sport_type, "timezone": club.timezone, "isAdmin": admin is not None}


@router.get("/summary", summary="클럽 요약(공개): 활동 멤버 · 올해 일정 · 올해 기사 수")
def get_summary(club: Club = Depends(club_dep), db: Session = Depends(get_db)):
    return club_service.club_summary(db, club, local_today(club.timezone))


@router.post("/admin/auth", summary="관리자 모드 진입(PIN 입력 → 토큰)")
def admin_auth(body: AdminAuthRequest, request: Request, club: Club = Depends(club_dep), db: Session = Depends(get_db)):
    client = request.client.host if request.client else "unknown"
    token, expires = club_service.admin_login(db, club, body.password, client)
    return {"accessToken": token, "tokenType": "Bearer", "expiresAt": to_iso(expires.replace(tzinfo=None))}


@router.get("/admin/me", summary="관리자 모드 확인")
def admin_me(admin: AdminPrincipal = Depends(admin_dep)):
    return {"clubId": admin.club_id, "adminId": admin.admin_id, "isAdmin": True}


@router.post("/admin/pin", summary="관리자 암호 변경")
def change_pin(body: ChangePinRequest, club: Club = Depends(club_dep), admin: AdminPrincipal = Depends(admin_dep),
               db: Session = Depends(get_db)):
    club_service.set_admin_pin(db, club.club_id, body.new_password)
    return {"ok": True}


@router.get("/admin/config", summary="운영 설정 조회")
def get_config(club: Club = Depends(club_dep), admin: AdminPrincipal = Depends(admin_dep), db: Session = Depends(get_db)):
    cfg = config_service.load_config(db, club.club_id)
    return {"configVersion": cfg.version, "items": config_service.list_config(db, club.club_id)}


@router.patch("/admin/config", summary="운영 설정 변경(이력/버전 기록)")
def patch_config(body: ConfigUpdateRequest, club: Club = Depends(club_dep), admin: AdminPrincipal = Depends(admin_dep),
                 db: Session = Depends(get_db)):
    cfg = config_service.update_config(db, club.club_id, body.values, admin.admin_id)
    return {"configVersion": cfg.version, "items": config_service.list_config(db, club.club_id)}


@router.get("/admin/config/history", summary="설정 변경 이력")
def config_history(club: Club = Depends(club_dep), admin: AdminPrincipal = Depends(admin_dep),
                   db: Session = Depends(get_db)):
    return [
        {"key": h.config_key, "before": h.before_value, "after": h.after_value, "configVersion": h.config_version,
         "changedAt": to_iso(h.changed_at), "adminId": h.changed_by_admin_id}
        for h in config_service.config_history(db, club.club_id)
    ]
