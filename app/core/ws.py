"""WebSocket 브로드캐스트 허브.

- 쓰기 요청(REST, 관리자)은 동기 스레드에서 실행되고, WebSocket은 이벤트 루프에서 돈다.
  publish()는 스레드 안전하게 루프로 메시지를 넘긴다.
- 채널 단위는 클럽(club:{id}). 클라이언트가 matchId/sessionId로 필터한다.
- 단일 프로세스 기준 구현. 다중 인스턴스로 늘릴 때는 Redis Pub/Sub 등으로 교체한다.
"""
import asyncio
import threading
from typing import Any


class Hub:
    def __init__(self) -> None:
        self.loop: asyncio.AbstractEventLoop | None = None
        self._channels: dict[str, set[asyncio.Queue]] = {}
        self._lock = threading.Lock()

    def bind_loop(self, loop: asyncio.AbstractEventLoop) -> None:
        self.loop = loop

    def subscribe(self, channel: str) -> asyncio.Queue:
        q: asyncio.Queue = asyncio.Queue(maxsize=1000)
        with self._lock:
            self._channels.setdefault(channel, set()).add(q)
        return q

    def unsubscribe(self, channel: str, q: asyncio.Queue) -> None:
        with self._lock:
            subs = self._channels.get(channel)
            if subs:
                subs.discard(q)
                if not subs:
                    self._channels.pop(channel, None)

    def subscriber_count(self, channel: str) -> int:
        with self._lock:
            return len(self._channels.get(channel, ()))

    def publish(self, channel: str, message: dict[str, Any]) -> None:
        loop = self.loop
        if loop is None or loop.is_closed():
            return
        with self._lock:
            targets = list(self._channels.get(channel, ()))
        for q in targets:
            loop.call_soon_threadsafe(_safe_put, q, message)


def _safe_put(q: asyncio.Queue, message: dict) -> None:
    try:
        q.put_nowait(message)
    except asyncio.QueueFull:
        pass  # 느린 구독자는 메시지를 잃는다. 클라이언트는 재접속 시 GET으로 상태 복원.


hub = Hub()


def club_channel(club_id: int) -> str:
    return f"club:{club_id}"
