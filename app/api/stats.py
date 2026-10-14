"""통계(공개) / Rating(관리자·디버그 전용) / 재계산."""
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.deps import admin_dep, club_dep
from app.core.database import get_db
from app.core.security import AdminPrincipal
from app.core.timeutil import to_iso, utcnow
from app.models import Club
from app.services import lifecycle_service, rating_service, stats_service
from app.services.common import get_member

router = APIRouter(tags=["stats"])


@router.get("/stats/members", summary="개인 통계 목록(공개)")
def member_stats(club: Club = Depends(club_dep), db: Session = Depends(get_db)):
    return stats_service.member_summaries(db, club.club_id)


@router.get("/stats/members/{member_id}", summary="개인 상세 통계: 최근 폼, 자주 같은 팀, 자주 만난 상대(공개)")
def member_detail(member_id: int, club: Club = Depends(club_dep), db: Session = Depends(get_db)):
    m = get_member(db, club.club_id, member_id)
    return stats_service.member_detail(db, club.club_id, m)


@router.get("/stats/pairs", summary="두 선수 관계(같이 뛴 기록 / 상대 전적, 공개)")
def pair_stats(a: int = Query(..., alias="memberA"), b: int = Query(..., alias="memberB"), club: Club = Depends(club_dep),
               db: Session = Depends(get_db)):
    get_member(db, club.club_id, a)
    get_member(db, club.club_id, b)
    return stats_service.head_to_head(db, club.club_id, a, b)


@router.get("/admin/ratings", summary="[관리자] 현재 Hidden Rating / Confidence")
def ratings(club: Club = Depends(club_dep), admin: AdminPrincipal = Depends(admin_dep), db: Session = Depends(get_db)):
    return rating_service.rating_rows(db, club.club_id, utcnow().date())


@router.get("/admin/ratings/{member_id}/history", summary="[관리자] Rating 변경 이력")
def rating_history(member_id: int, include_voided: bool = Query(False, alias="includeVoided"),
                   club: Club = Depends(club_dep), admin: AdminPrincipal = Depends(admin_dep),
                   db: Session = Depends(get_db)):
    return [
        {"ratingHistoryId": h.rating_history_id, "before": round(h.before_rating, 3), "after": round(h.after_rating, 3),
         "change": round(h.change_amount, 3), "beforeConfidence": round(h.before_confidence, 4),
         "afterConfidence": round(h.after_confidence, 4), "reason": h.change_reason,
         "referenceType": h.reference_type, "referenceId": h.reference_id, "algorithmVersion": h.algorithm_version,
         "configVersion": h.config_version, "detail": h.calc_detail_json, "voided": h.voided_yn,
         "createdAt": to_iso(h.created_at)}
        for h in rating_service.rating_history(db, club.club_id, member_id, include_voided)
    ]


@router.post("/admin/rebuild", summary="[관리자] Rating/통계/Pair 전체 재계산")
def rebuild(club: Club = Depends(club_dep), admin: AdminPrincipal = Depends(admin_dep), db: Session = Depends(get_db)):
    return lifecycle_service.rebuild_everything(db, club.club_id)
