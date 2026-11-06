"""원정팀 목록: 조회(공개, 숨긴 팀 포함은 관리자) / [직접추가] · 이름 수정 · 숨기기 · 복원(관리자)."""
from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy.orm import Session

from app.api.deps import admin_dep, club_dep, optional_admin
from app.core.database import get_db
from app.core.errors import Unauthorized
from app.core.security import AdminPrincipal
from app.models import Club
from app.schemas.requests import OpponentCreate, OpponentUpdate
from app.services import opponent_service

router = APIRouter(tags=["sessions"])


@router.get("/opponents", summary="원정팀 목록(원정 경기 상대는 이 목록에서만 고른다). includeHidden=true = 숨긴 팀 포함(관리자)")
def list_opponents(include_hidden: bool = Query(False, alias="includeHidden"), club: Club = Depends(club_dep),
                   admin: AdminPrincipal | None = Depends(optional_admin), db: Session = Depends(get_db)):
    if include_hidden and admin is None:
        raise Unauthorized("관리자 모드가 필요합니다.", "ADMIN_REQUIRED")
    counts = opponent_service.session_counts(db, club.club_id) if include_hidden else None
    return [opponent_service.serialize_opponent(o, counts.get(o.opponent_id, 0) if counts is not None else None)
            for o in opponent_service.list_opponents(db, club.club_id, include_hidden)]


@router.post("/opponents", status_code=201,
             summary="원정팀 [직접추가](같은 이름이 있으면 그 팀을 200으로 돌려줌, 공백 · 대소문자 무시)")
def create_opponent(body: OpponentCreate, response: Response, club: Club = Depends(club_dep),
                    admin: AdminPrincipal = Depends(admin_dep), db: Session = Depends(get_db)):
    o, created = opponent_service.create_opponent(db, club.club_id, body.name)
    if not created:
        response.status_code = 200
    return opponent_service.serialize_opponent(o)


@router.patch("/opponents/{opponent_id}",
              summary="[원정팀 관리] 이름 수정(지난 원정 일정 표시도 새 이름으로) · 숨기기(active=false, 지난 전적 유지) · 복원")
def update_opponent(opponent_id: int, body: OpponentUpdate, club: Club = Depends(club_dep),
                    admin: AdminPrincipal = Depends(admin_dep), db: Session = Depends(get_db)):
    o = opponent_service.update_opponent(db, club.club_id, opponent_id, name=body.name, active=body.active)
    return opponent_service.serialize_opponent(o, opponent_service.session_counts(db, club.club_id).get(o.opponent_id, 0))
