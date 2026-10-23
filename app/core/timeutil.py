"""시간 처리 규칙.

- DB DATETIME은 전부 UTC(naive)로 저장한다.
- SESSION_DATE처럼 명확한 현지 날짜는 DATE로 저장한다.
- API 응답은 ISO-8601 + 'Z'로 내보낸다. 화면 변환(Asia/Seoul)은 클라이언트 몫.
"""
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


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


# 시간대 DB(tzdata)가 없는 환경(Windows 기본 Python)용 대체값. 서머타임 없는 시간대만 둔다
_FIXED_OFFSETS = {"Asia/Seoul": 9, "Asia/Tokyo": 9, "UTC": 0}


def club_tz(tz: str):
    """클럽 시간대. ZoneInfo를 못 찾으면(tzdata 미설치) 고정 오프셋, 그것도 없으면 UTC."""
    try:
        return ZoneInfo(tz)
    except (ZoneInfoNotFoundError, ValueError):
        return timezone(timedelta(hours=_FIXED_OFFSETS.get(tz, 0)))


def local_today(tz: str) -> date:
    """클럽 현지 날짜(예: Asia/Seoul). 서버 시각은 UTC라 자정 무렵 날짜가 다를 수 있어 구분한다."""
    return utcnow().replace(tzinfo=timezone.utc).astimezone(club_tz(tz)).date()
