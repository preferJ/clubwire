"""LIVE 경기 자동 종료 감시 루프(AUTO_END_YN=true 경기). DB에 매초 기록하지 않는다."""
import asyncio
import logging

from starlette.concurrency import run_in_threadpool

from app.core.config import settings
from app.services.match_service import auto_end_due_matches

log = logging.getLogger("clubwire.timer")


async def timer_loop() -> None:
    while True:
        await asyncio.sleep(settings.TIMER_TICK_SEC)
        try:
            await run_in_threadpool(auto_end_due_matches)
        except asyncio.CancelledError:
            raise
        except Exception:  # noqa: BLE001
            log.exception("timer loop error")
