from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.deps import admin_dep, club_dep, optional_admin
from app.core.database import get_db
from app.core.security import AdminPrincipal
from app.models import Club, Member
from app.schemas.requests import MemberCreate, MemberUpdate
from app.services import member_service

router = APIRouter(prefix="/members", tags=["members"])


def _m(m: Member) -> dict:
    return {"memberId": m.member_id, "name": m.name, "active": m.active_yn, "joinedAt": m.joined_at,
            "profileImageUrl": m.profile_image_url, "displayOrder": m.display_order}


@router.get("", summary="멤버 목록(공개)")
def list_members(include_inactive: bool = Query(False, alias="includeInactive"), club: Club = Depends(club_dep),
                 admin: AdminPrincipal | None = Depends(optional_admin), db: Session = Depends(get_db)):
    return [_m(m) for m in member_service.list_members(db, club.club_id, include_inactive and admin is not None)]


@router.post("", status_code=201, summary="멤버 등록")
def create_member(body: MemberCreate, club: Club = Depends(club_dep), admin: AdminPrincipal = Depends(admin_dep),
                  db: Session = Depends(get_db)):
    return _m(member_service.create_member(db, club.club_id, body.name, body.joined_at, body.profile_image_url,
                                           body.display_order))


@router.patch("/{member_id}", summary="멤버 수정/비활성화(active=false). 삭제는 하지 않음")
def update_member(member_id: int, body: MemberUpdate, club: Club = Depends(club_dep),
                  admin: AdminPrincipal = Depends(admin_dep), db: Session = Depends(get_db)):
    return _m(member_service.update_member(db, club.club_id, member_id, name=body.name, joined_at=body.joined_at,
                                           profile_image_url=body.profile_image_url,
                                           display_order=body.display_order, active_yn=body.active))
