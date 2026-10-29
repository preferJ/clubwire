"""슈퍼관리자의 운영팀 관리 API. 모든 동작에 전역 관리자 인증이 필요하다."""
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.superadmin import superadmin_dep
from app.schemas.superadmin import SuperAdminClubCreate, SuperAdminClubUpdate
from app.services import superadmin_service


router = APIRouter(prefix="/api/admin/clubs", tags=["superadmin"], dependencies=[Depends(superadmin_dep)])


@router.get("", summary="슈퍼관리자: 운영팀 목록")
def list_clubs(db: Session = Depends(get_db)):
    return superadmin_service.list_clubs(db)


@router.post("", status_code=201, summary="슈퍼관리자: 운영팀 추가")
def create_club(body: SuperAdminClubCreate, db: Session = Depends(get_db)):
    return superadmin_service.create_club(db, **body.model_dump())


@router.patch("/{club_id}", summary="슈퍼관리자: 운영팀 수정")
def update_club(club_id: int, body: SuperAdminClubUpdate, db: Session = Depends(get_db)):
    return superadmin_service.update_club(db, club_id, body.model_dump(exclude_unset=True))


@router.delete("/{club_id}", summary="슈퍼관리자: 팀 제거(기록 보존·접근 중지)")
def remove_club(club_id: int, db: Session = Depends(get_db)):
    return superadmin_service.set_club_active(db, club_id, False)


@router.post("/{club_id}/restore", summary="슈퍼관리자: 제거된 팀 복원")
def restore_club(club_id: int, db: Session = Depends(get_db)):
    return superadmin_service.set_club_active(db, club_id, True)
