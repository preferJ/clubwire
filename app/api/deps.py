from collections.abc import Iterable

from fastapi import BackgroundTasks, Depends, Path
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.database import get_db
from app.core.errors import Forbidden, Unauthorized
from app.core.security import AdminPrincipal, decode_admin_token
from app.models import Club
from app.services.common import get_club_by_slug
from app.wire.article_service import run_generation

_bearer = HTTPBearer(auto_error=False, description="관리자 모드 토큰: POST /admin/auth 로 발급")


def club_dep(club_slug: str = Path(..., description="클럽 주소(slug)"), db: Session = Depends(get_db)) -> Club:
    return get_club_by_slug(db, club_slug)


def optional_admin(
    club: Club = Depends(club_dep), cred: HTTPAuthorizationCredentials | None = Depends(_bearer)
) -> AdminPrincipal | None:
    if not cred:
        return None
    p = decode_admin_token(cred.credentials)
    return p if p.club_id == club.club_id else None


def admin_dep(
    club: Club = Depends(club_dep), cred: HTTPAuthorizationCredentials | None = Depends(_bearer)
) -> AdminPrincipal:
    if not cred:
        raise Unauthorized("관리자 모드가 필요합니다.", "ADMIN_REQUIRED")
    p = decode_admin_token(cred.credentials)
    if p.club_id != club.club_id:
        raise Forbidden("다른 클럽의 관리자 토큰입니다.", "WRONG_CLUB")
    return p


def schedule_articles(background: BackgroundTasks, article_ids: Iterable[int]) -> None:
    """기사 생성은 OpenAI 호출이 길어 응답 이후 백그라운드에서 실행."""
    for aid in article_ids:
        if settings.ARTICLE_GENERATION_SYNC:
            run_generation(aid)
        else:
            background.add_task(run_generation, aid)
