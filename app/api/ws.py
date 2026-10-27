"""WebSocket: 누구나 구독(조회 전용). 쓰기는 REST + 관리자 토큰.

메시지 종류
  HELLO           접속 직후 {serverTime}
  MATCH_UPDATED   {matchId, sessionId, match: 경기 상태(타이머 원본 포함)}
  MATCH_EVENT     {matchId, sessionId, event}
  SESSION_UPDATED {sessionId, status}
  TEAMS_UPDATED   {sessionId}
  ARTICLE_UPDATED {articleId, status}
  TITLE_UPDATED   {memberTitleId}
  CLUB_CONTENT_UPDATED  {} 운영수칙 또는 상단 공지 변경
클라이언트 → 서버: "ping" 텍스트를 보내면 {"type":"PONG"} 응답.

타이머는 매초 보내지 않는다. 클라이언트는 MATCH_UPDATED의 startedAt/pausedSeconds/serverTime으로 직접 계산한다.
"""
import asyncio

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from starlette.concurrency import run_in_threadpool

from app.core.database import SessionLocal
from app.core.errors import NotFound
from app.core.timeutil import to_iso, utcnow
from app.core.ws import club_channel, hub
from app.services.common import get_club_by_slug

router = APIRouter()


def _resolve_club_id(slug: str) -> int | None:
    with SessionLocal() as db:
        try:
            return get_club_by_slug(db, slug).club_id
        except NotFound:
            return None


@router.websocket("/ws/clubs/{club_slug}")
async def club_ws(websocket: WebSocket, club_slug: str):
    club_id = await run_in_threadpool(_resolve_club_id, club_slug)
    if club_id is None:
        await websocket.close(code=4404)
        return
    await websocket.accept()
    channel = club_channel(club_id)
    queue = hub.subscribe(channel)
    await websocket.send_json({"type": "HELLO", "clubId": club_id, "serverTime": to_iso(utcnow())})

    async def pump_out():
        while True:
            msg = await queue.get()
            await websocket.send_json(msg)

    async def pump_in():
        while True:
            text = await websocket.receive_text()
            if text.strip().lower() == "ping":
                await websocket.send_json({"type": "PONG", "serverTime": to_iso(utcnow())})

    out_task = asyncio.create_task(pump_out())
    in_task = asyncio.create_task(pump_in())
    try:
        done, pending = await asyncio.wait({out_task, in_task}, return_when=asyncio.FIRST_COMPLETED)
        for t in pending:
            t.cancel()
        for t in done:
            exc = t.exception()
            if exc and not isinstance(exc, WebSocketDisconnect):
                raise exc
    except WebSocketDisconnect:
        pass
    finally:
        out_task.cancel()
        in_task.cancel()
        hub.unsubscribe(channel, queue)
