from datetime import date

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.deps import admin_dep, club_dep
from app.core.database import get_db
from app.core.security import AdminPrincipal
from app.models import Club, TitleType
from app.schemas.requests import TitleAwardRequest, TitleTypeCreate, TitleTypeUpdate
from app.services import title_service

router = APIRouter(prefix="/titles", tags=["titles"])


def _t(t: TitleType) -> dict:
    return {"titleTypeId": t.title_type_id, "titleCode": t.title_code, "titleName": t.title_name,
            "periodType": t.period_type, "awardMethod": t.award_method, "autoRule": t.auto_rule,
            "countsAsMvp": t.counts_as_mvp_yn, "active": t.active_yn, "displayOrder": t.display_order}


@router.get("/types", summary="타이틀 종류(공개)")
def list_types(club: Club = Depends(club_dep), db: Session = Depends(get_db)):
    return [_t(t) for t in title_service.list_title_types(db, club.club_id)]


@router.post("/types", status_code=201, summary="타이틀 종류 추가")
def create_type(body: TitleTypeCreate, club: Club = Depends(club_dep), admin: AdminPrincipal = Depends(admin_dep),
                db: Session = Depends(get_db)):
    return _t(title_service.create_title_type(
        db, club.club_id, title_code=body.title_code, title_name=body.title_name, period_type=body.period_type,
        award_method=body.award_method, auto_rule=body.auto_rule, counts_as_mvp=body.counts_as_mvp,
        display_order=body.display_order))


@router.patch("/types/{title_type_id}", summary="타이틀 종류 수정/비활성화")
def update_type(title_type_id: int, body: TitleTypeUpdate, club: Club = Depends(club_dep),
                admin: AdminPrincipal = Depends(admin_dep), db: Session = Depends(get_db)):
    return _t(title_service.update_title_type(db, club.club_id, title_type_id, title_name=body.title_name,
                                              active_yn=body.active, display_order=body.display_order,
                                              counts_as_mvp_yn=body.counts_as_mvp))


@router.get("/awards", summary="타이틀 수여 이력(공개)")
def list_awards(member_id: int | None = Query(None, alias="memberId"), date_from: date | None = Query(None, alias="from"),
                date_to: date | None = Query(None, alias="to"),
                title_code: str | None = Query(None, alias="titleCode", description="타이틀 코드. 'ATTEND_STREAK_'처럼 _로 끝나면 앞부분 일치"),
                limit: int = Query(100, ge=1, le=1000), club: Club = Depends(club_dep), db: Session = Depends(get_db)):
    return title_service.list_awards(db, club.club_id, member_id=member_id, date_from=date_from, date_to=date_to,
                                     title_code=title_code, limit=limit)


@router.post("/awards", status_code=201, summary="타이틀 수여(수동 타이틀. 기본 타이틀은 모두 자동 집계)")
def award(body: TitleAwardRequest, club: Club = Depends(club_dep), admin: AdminPrincipal = Depends(admin_dep),
          db: Session = Depends(get_db)):
    mt = title_service.award_title(db, club.club_id, admin.admin_id, title_code=body.title_code,
                                   member_id=body.member_id, award_date=body.award_date, session_id=body.session_id,
                                   note=body.note)
    return {"memberTitleId": mt.member_title_id, "periodStart": mt.period_start, "periodEnd": mt.period_end}


@router.post("/awards/{member_title_id}/cancel", summary="타이틀 수여 취소")
def cancel_award(member_title_id: int, club: Club = Depends(club_dep), admin: AdminPrincipal = Depends(admin_dep),
                 db: Session = Depends(get_db)):
    title_service.cancel_award(db, club.club_id, member_title_id)
    return {"ok": True}
