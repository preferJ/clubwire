"""DB 연결과 트랜잭션 경계.

- 서비스 함수가 명시적으로 commit 한다(작업 단위 = 서비스 함수 1개).
- WebSocket 알림은 emit()으로 세션에 쌓아 두었다가 COMMIT 성공 후에만 발송한다.
  (롤백된 변경이 화면에 보이는 일을 막기 위함)
"""
from collections.abc import Iterator
from typing import Any

from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import settings
from app.core.ws import club_channel, hub

engine = create_engine(
    settings.DATABASE_URL,
    echo=settings.SQL_ECHO,
    pool_pre_ping=True,
    pool_recycle=3600,
    isolation_level="READ COMMITTED",  # 행 잠금 이후 최신 커밋 값을 읽도록(멱등키/동시 득점 처리)
)

SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)

_WS_KEY = "ws_events"


def emit(db: Session, club_id: int, event_type: str, payload: dict[str, Any]) -> None:
    db.info.setdefault(_WS_KEY, []).append((club_id, {"type": event_type, **payload}))


@event.listens_for(Session, "after_commit")
def _publish_after_commit(db: Session) -> None:
    events = db.info.pop(_WS_KEY, None)
    if not events:
        return
    for club_id, message in events:
        hub.publish(club_channel(club_id), message)


@event.listens_for(Session, "do_orm_execute")
def _refresh_locked_rows(state) -> None:
    """SELECT … FOR UPDATE 결과는 항상 DB 최신값으로 덮어쓴다.

    같은 요청에서 잠금 없이 먼저 읽어 둔 객체(identity map)가 있으면, 잠금 조회를 해도
    옛 값이 그대로 남아 이중 종료/버전 역행이 생길 수 있다.
    """
    if state.is_select and getattr(state.statement, "_for_update_arg", None) is not None:
        state.update_execution_options(populate_existing=True)


@event.listens_for(Session, "after_rollback")
def _discard_after_rollback(db: Session) -> None:
    db.info.pop(_WS_KEY, None)


def get_db() -> Iterator[Session]:
    db = SessionLocal()
    try:
        yield db
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()
