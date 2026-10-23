"""이달의 MVP 월 마감 감시 루프: 서버가 켜질 때 한 번, 이후 MONTHLY_CHECK_SEC마다 지난달 마감 여부를 확인한다."""
import asyncio
import logging

from sqlalchemy import select
from starlette.concurrency import run_in_threadpool

from app.core.config import settings
from app.core.database import SessionLocal
from app.models import Club
from app.services.mvp_service import close_due_month
from app.wire.article_service import run_generation

log = logging.getLogger("clubwire.monthly")


def run_monthly_close() -> list[int]:
    """모든 활성 클럽의 지난달을 마감(가능한 경우)하고 MVP 기사를 만든다. 반환: 만든 기사 ID."""
    article_ids: list[int] = []
    with SessionLocal() as db:
        for club in db.scalars(select(Club).where(Club.active_yn.is_(True))).all():
            try:
                article_ids += close_due_month(db, club)
            except Exception:  # noqa: BLE001  한 클럽 실패가 다른 클럽을 막지 않게
                db.rollback()
                log.exception("monthly close failed: club %s", club.club_id)
    for aid in article_ids:
        run_generation(aid)  # 이 스레드에서 바로 작성 · 게시
    return article_ids


async def monthly_loop() -> None:
    while True:
        try:
            await run_in_threadpool(run_monthly_close)
        except asyncio.CancelledError:
            raise
        except Exception:  # noqa: BLE001
            log.exception("monthly loop error")
        await asyncio.sleep(settings.MONTHLY_CHECK_SEC)
