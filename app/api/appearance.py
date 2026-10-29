"""클럽별 공개 외형과 관리자 외형 편집. 모든 데이터는 URL의 클럽에 귀속된다."""
from fastapi import APIRouter, Depends, Request, Response
from sqlalchemy.orm import Session

from app.api.deps import admin_dep, club_dep
from app.core.database import get_db
from app.core.security import AdminPrincipal
from app.models import Club
from app.schemas.appearance import ClubAppearanceUpdate
from app.services import club_appearance_service


router = APIRouter(tags=["club-appearance"])


@router.get("/appearance", summary="클럽 엠블럼과 기본 테마 조회")
def get_appearance(club: Club = Depends(club_dep)):
    return club_appearance_service.serialize_appearance(club)


@router.patch("/admin/appearance", summary="클럽 엠블럼과 기본 테마 저장")
def patch_appearance(body: ClubAppearanceUpdate, club: Club = Depends(club_dep),
                     admin: AdminPrincipal = Depends(admin_dep), db: Session = Depends(get_db)):
    updated = club_appearance_service.update_appearance(db, club.club_id, body.model_dump(exclude_unset=True))
    return club_appearance_service.serialize_appearance(updated)


@router.get("/appearance/crest", summary="공개 이미지 엠블럼(PNG)")
def get_crest_image(request: Request, club: Club = Depends(club_dep)):
    content = club_appearance_service.crest_image(club)
    digest = club_appearance_service.image_digest(content)
    etag = f'"{digest}"'
    version_matches = request.query_params.get("v") == digest[:16]
    headers = {
        "ETag": etag,
        "X-Content-Type-Options": "nosniff",
        "Cache-Control": "public, max-age=31536000, immutable" if version_matches else "no-cache",
    }
    matches = {value.strip() for value in request.headers.get("if-none-match", "").split(",")}
    if etag in matches or f"W/{etag}" in matches or "*" in matches:
        return Response(status_code=304, headers=headers)
    return Response(content=content, media_type="image/png", headers=headers)
