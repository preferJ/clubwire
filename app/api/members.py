from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.deps import admin_dep, club_dep, optional_admin
from app.core.database import get_db
from app.core.errors import Unauthorized
from app.core.security import AdminPrincipal
from app.core.timeutil import to_iso
from app.models import Club, Member
from app.schemas.requests import MemberCreate, MemberUpdate
from app.services import member_service

router = APIRouter(prefix="/members", tags=["members"])


def _m(m: Member) -> dict:
    return {"memberId": m.member_id, "name": m.name, "active": m.active_yn, "joinedAt": m.joined_at,
            "birthYear": m.birth_year, "jerseyNumber": m.jersey_number,
            "profileImageUrl": m.profile_image_url, "displayOrder": m.display_order,
            "deleted": m.deleted_at is not None, "deletedAt": to_iso(m.deleted_at)}


@router.get("", summary="멤버 목록(공개, 삭제한 선수 제외). 관리자: includeInactive=true면 비활성 포함, deleted=true면 삭제한 선수만")
def list_members(include_inactive: bool = Query(False, alias="includeInactive"), deleted: bool = Query(False),
                 club: Club = Depends(club_dep), admin: AdminPrincipal | None = Depends(optional_admin),
                 db: Session = Depends(get_db)):
    if deleted and admin is None:
        raise Unauthorized("관리자 모드가 필요합니다.", "ADMIN_REQUIRED")
    return [_m(m) for m in member_service.list_members(db, club.club_id, include_inactive and admin is not None, deleted)]


@router.post("", status_code=201, summary="멤버 등록")
def create_member(body: MemberCreate, club: Club = Depends(club_dep), admin: AdminPrincipal = Depends(admin_dep),
                  db: Session = Depends(get_db)):
    return _m(member_service.create_member(db, club.club_id, body.name, body.joined_at, body.profile_image_url,
                                           body.display_order, body.initial_rating, body.birth_year, body.jersey_number))


@router.patch("/{member_id}", summary="멤버 수정/비활성화(active=false). 가입일·출생연도·등번호는 null로 지울 수 있음. 삭제한 선수는 409")
def update_member(member_id: int, body: MemberUpdate, club: Club = Depends(club_dep),
                  admin: AdminPrincipal = Depends(admin_dep), db: Session = Depends(get_db)):
    fields = dict(name=body.name, profile_image_url=body.profile_image_url, display_order=body.display_order,
                  active_yn=body.active)
    # 가입일·출생연도·등번호: 보낸 항목만 반영(null = 지움). 안 보낸 항목은 그대로
    for k in member_service.CLEARABLE:
        if k in body.model_fields_set:
            fields[k] = getattr(body, k)
    return _m(member_service.update_member(db, club.club_id, member_id, **fields))


@router.delete("/{member_id}", summary="선수 삭제(목록 · 참석 선택 · 기록 순위에서 숨김, DB 행과 지난 기록은 보존). 끝나지 않은 일정 참석자는 409")
def delete_member(member_id: int, club: Club = Depends(club_dep), admin: AdminPrincipal = Depends(admin_dep),
                  db: Session = Depends(get_db)):
    return _m(member_service.delete_member(db, club.club_id, member_id))


@router.post("/{member_id}/restore", summary="삭제한 선수 복원")
def restore_member(member_id: int, club: Club = Depends(club_dep), admin: AdminPrincipal = Depends(admin_dep),
                   db: Session = Depends(get_db)):
    return _m(member_service.restore_member(db, club.club_id, member_id))
