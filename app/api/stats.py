"""통계(공개) / 재계산.

Rating은 API로 내보내지 않는다(관리자 포함). 확인은 DB(PLAYER_RATING, PLAYER_RATING_HISTORY)에서만.
"""
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.deps import admin_dep, club_dep
from app.core.database import get_db
from app.core.security import AdminPrincipal
from app.models import Club
from app.services import away_service, lifecycle_service, mvp_service, stats_service
from app.services.common import get_member

router = APIRouter(tags=["stats"])


@router.get("/stats/members", summary="개인 통계 목록(공개)")
def member_stats(club: Club = Depends(club_dep), db: Session = Depends(get_db)):
    return stats_service.member_summaries(db, club.club_id)


@router.get("/stats/away", summary="원정 경기 기록(공개): 전체 · 상대별 전적, 최근 원정, 선수별 원정 기록. 내부 기록과 분리")
def away_stats(club: Club = Depends(club_dep), db: Session = Depends(get_db)):
    return away_service.away_overview(db, club.club_id)


@router.get("/stats/away/opponents/{opponent_id}",
            summary="원정 상대별 상세(공개): 그 팀과의 원정 일정 · 경기 점수 + 그 팀 상대 우리 선수 골 · 도움 기록(숨긴 팀도)")
def away_opponent_stats(opponent_id: int, club: Club = Depends(club_dep), db: Session = Depends(get_db)):
    return away_service.away_opponent(db, club.club_id, opponent_id)


@router.get("/stats/members/{member_id}", summary="개인 상세 통계: 최근 폼, 자주 같은 팀, 자주 만난 상대(공개)")
def member_detail(member_id: int, top: int = Query(5, ge=1, le=20, description="자주 같은 팀 · 맞붙은 선수 몇 명까지"),
                  club: Club = Depends(club_dep), db: Session = Depends(get_db)):
    m = get_member(db, club.club_id, member_id)
    data = stats_service.member_detail(db, club.club_id, m, top_n=top)
    data["away"] = away_service.away_member(db, club.club_id, m.member_id)  # 원정 기록(내부 기록과 별도)
    return data


@router.get("/stats/mvp-race", summary="이달의 MVP 후보 1~3위(실력 점수 상승률 %만, 점수 자체는 비공개) + 지난달 MVP(공개)")
def mvp_race(club: Club = Depends(club_dep), db: Session = Depends(get_db)):
    return mvp_service.mvp_race(db, club)


@router.get("/stats/pairs", summary="두 선수 관계(같이 뛴 기록 / 상대 전적, 공개)")
def pair_stats(a: int = Query(..., alias="memberA"), b: int = Query(..., alias="memberB"), club: Club = Depends(club_dep),
               db: Session = Depends(get_db)):
    get_member(db, club.club_id, a)
    get_member(db, club.club_id, b)
    return stats_service.head_to_head(db, club.club_id, a, b)


@router.post("/admin/rebuild", summary="[관리자] Rating/통계/Pair 전체 재계산")
def rebuild(club: Club = Depends(club_dep), admin: AdminPrincipal = Depends(admin_dep), db: Session = Depends(get_db)):
    return lifecycle_service.rebuild_everything(db, club.club_id)
