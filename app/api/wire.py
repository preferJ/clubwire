"""The Wire: 기사(공개는 게시본만) / Insight(관리자)."""
from fastapi import APIRouter, BackgroundTasks, Depends, Query
from sqlalchemy.orm import Session

from app.api.deps import admin_dep, club_dep, optional_admin, schedule_articles
from app.core.database import get_db
from app.core.security import AdminPrincipal
from app.models import Club
from app.schemas.requests import ArticleRegenerateRequest, ArticleUpdate
from app.wire import article_service

router = APIRouter(tags=["wire"])


@router.get("/articles", summary="기사 목록(공개: 게시본 / 관리자: all=true면 전체)")
def list_articles(tag: str | None = None, member_id: int | None = Query(None, alias="memberId"),
                  session_id: int | None = Query(None, alias="sessionId"), status: str | None = None,
                  all_: bool = Query(False, alias="all"), limit: int = Query(20, le=100),
                  before_id: int | None = Query(None, alias="beforeId"), club: Club = Depends(club_dep),
                  admin: AdminPrincipal | None = Depends(optional_admin), db: Session = Depends(get_db)):
    published_only = not (admin and all_)
    rows = article_service.list_articles(db, club.club_id, published_only=published_only, tag=tag, member_id=member_id,
                                         session_id=session_id, status=status, limit=limit, before_id=before_id)
    return [article_service.serialize_article(db, a, admin=admin is not None) for a in rows]


@router.get("/articles/{article_id}", summary="기사 상세")
def get_article(article_id: int, club: Club = Depends(club_dep), admin: AdminPrincipal | None = Depends(optional_admin),
                db: Session = Depends(get_db)):
    a = article_service.get_article(db, club.club_id, article_id, admin=admin is not None)
    return article_service.serialize_article(db, a, detail=True, admin=admin is not None)


@router.patch("/articles/{article_id}", summary="관리자 게시 전 기사 수정")
def update(article_id: int, body: ArticleUpdate, club: Club = Depends(club_dep),
           admin: AdminPrincipal = Depends(admin_dep), db: Session = Depends(get_db)):
    a = article_service.update_article(db, club.club_id, article_id, **body.model_dump())
    return article_service.serialize_article(db, a, detail=True, admin=True)


@router.post("/articles/{article_id}/publish", summary="기사 게시(같은 일정/종류의 기존 게시본은 SUPERSEDED)")
def publish(article_id: int, club: Club = Depends(club_dep), admin: AdminPrincipal = Depends(admin_dep),
            db: Session = Depends(get_db)):
    a = article_service.publish_article(db, club.club_id, article_id)
    return article_service.serialize_article(db, a, detail=True, admin=True)


@router.post("/articles/{article_id}/reject", summary="기사 반려/내리기")
def reject(article_id: int, club: Club = Depends(club_dep), admin: AdminPrincipal = Depends(admin_dep),
           db: Session = Depends(get_db)):
    a = article_service.reject_article(db, club.club_id, article_id)
    return article_service.serialize_article(db, a, detail=True, admin=True)


@router.post("/articles/{article_id}/regenerate", status_code=201, summary="기사 재생성(새 버전, 기존 보존)")
def regenerate(article_id: int, background: BackgroundTasks, club: Club = Depends(club_dep),
               admin: AdminPrincipal = Depends(admin_dep), db: Session = Depends(get_db),
               body: ArticleRegenerateRequest | None = None):
    a = article_service.regenerate_article(
        db, club.club_id, article_id, required_insight_ids=body.required_insight_ids if body else None,
    )
    schedule_articles(background, [a.article_id])
    db.refresh(a)
    return article_service.serialize_article(db, a, detail=True, admin=True)


@router.get("/admin/insights", summary="[관리자] Insight 목록")
def list_insights(session_id: int | None = Query(None, alias="sessionId"),
                  include_inactive: bool = Query(False, alias="includeInactive"), club: Club = Depends(club_dep),
                  admin: AdminPrincipal = Depends(admin_dep), db: Session = Depends(get_db)):
    return article_service.list_insights(db, club.club_id, session_id, include_inactive)
