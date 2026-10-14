"""시간 처리 규칙.

- DB DATETIME은 전부 UTC(naive)로 저장한다.
- SESSION_DATE처럼 명확한 현지 날짜는 DATE로 저장한다.
- API 응답은 ISO-8601 + 'Z'로 내보낸다. 화면 변환(Asia/Seoul)은 클라이언트 몫.
"""
from datetime import date, datetime, timedelta, timezone


def utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def to_iso(dt: datetime | None) -> str | None:
    if dt is None:
        return None
    return dt.replace(microsecond=(dt.microsecond // 1000) * 1000).isoformat(timespec="milliseconds") + "Z"


def week_range(d: date) -> tuple[date, date]:
    """해당 날짜가 속한 주(월~일)."""
    start = d - timedelta(days=d.weekday())
    return start, start + timedelta(days=6)
