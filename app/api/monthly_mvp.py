"""월간 순위는 공개 참고용으로 유지하고, MVP 수상자는 관리자가 직접 선정한다."""
from fastapi import APIRouter, BackgroundTasks, Depends, Query
from pydantic import Field
from sqlalchemy.orm import Session

from app.api.deps import admin_dep, club_dep, schedule_articles
from app.core.database import get_db
from app.core.security import AdminPrincipal
from app.models import Club
from app.schemas.requests import CamelModel
from app.services import mvp_service

router = APIRouter(tags=["monthly-mvp"])


class MonthlyMvpSelection(CamelModel):
    month: str = Field(pattern=r"^\d{4}-\d{2}$")
    replace: bool = False


@router.get("/monthly-mvp", summary="관리자: 월별 MVP 선정 상태")
def selection(month: str = Query(pattern=r"^\d{4}-\d{2}$"), club: Club = Depends(club_dep),
              admin: AdminPrincipal = Depends(admin_dep), db: Session = Depends(get_db)):
    return mvp_service.monthly_selection(db, club, month)


@router.post("/members/{member_id}/monthly-mvp", summary="관리자가 이달의 MVP를 선정하고 발표 기사를 생성")
def select_mvp(member_id: int, body: MonthlyMvpSelection, background: BackgroundTasks,
               club: Club = Depends(club_dep), admin: AdminPrincipal = Depends(admin_dep),
               db: Session = Depends(get_db)):
    result = mvp_service.select_monthly_mvp(db, club, member_id, body.month, admin.admin_id, replace=body.replace)
    if result["changed"]:
        schedule_articles(background, [result["articleId"]])
    return result
