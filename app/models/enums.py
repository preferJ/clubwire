"""상태/코드 값. DB에는 VARCHAR로 저장하고 애플리케이션 Enum으로 검증한다."""
from enum import StrEnum


class SportType(StrEnum):
    FUTSAL = "FUTSAL"


class SessionStatus(StrEnum):
    OPEN = "OPEN"              # 참석자 모집/팀 편성 미확정
    CONFIRMED = "CONFIRMED"    # [일정확정] 팀 확정 → PRE_MATCH 기사
    IN_PROGRESS = "IN_PROGRESS"  # 첫 경기 시작
    CLOSED = "CLOSED"          # [일정마감] 수정 불가 → SESSION_RECAP 기사
    CANCELLED = "CANCELLED"


class AttendanceStatus(StrEnum):
    ATTENDING = "ATTENDING"
    ABSENT = "ABSENT"
    PENDING = "PENDING"


class AssignType(StrEnum):
    AUTO = "AUTO"
    MANUAL = "MANUAL"


class GenerationStatus(StrEnum):
    PREVIEW = "PREVIEW"
    CONFIRMED = "CONFIRMED"
    DISCARDED = "DISCARDED"


class AssignmentAction(StrEnum):
    ADD = "ADD"
    MOVE = "MOVE"
    REMOVE = "REMOVE"


class GameStatus(StrEnum):
    READY = "READY"
    RUNNING = "RUNNING"
    PAUSED = "PAUSED"
    FINISHED = "FINISHED"
    CANCELLED = "CANCELLED"


class EndReason(StrEnum):
    ADMIN = "ADMIN"
    TIME_UP = "TIME_UP"
    EARLY_GOAL = "EARLY_GOAL"
    SESSION_CLOSE = "SESSION_CLOSE"


class EventType(StrEnum):
    START = "START"
    PAUSE = "PAUSE"
    RESUME = "RESUME"
    GOAL = "GOAL"
    GOAL_CANCEL = "GOAL_CANCEL"
    END = "END"
    FINALIZE = "FINALIZE"
    UNFINALIZE = "UNFINALIZE"
    CANCEL = "CANCEL"
    MEMBER_ADD = "MEMBER_ADD"
    MEMBER_REMOVE = "MEMBER_REMOVE"


class RatingChangeReason(StrEnum):
    MATCH_RESULT = "MATCH_RESULT"
    ADMIN_RECALC = "ADMIN_RECALC"


class ReferenceType(StrEnum):
    MATCH = "MATCH"


class TitlePeriodType(StrEnum):
    WEEKLY = "WEEKLY"
    SESSION = "SESSION"
    MONTHLY = "MONTHLY"   # 이달의 MVP(월 마감 때 자동 집계)


class AwardMethod(StrEnum):
    MANUAL = "MANUAL"
    AUTO = "AUTO"


class TitleAutoRule(StrEnum):
    TOP_GOALS = "TOP_GOALS"
    TOP_ASSISTS = "TOP_ASSISTS"
    TOP_WINS = "TOP_WINS"
    MONTHLY_RATING_RISE = "MONTHLY_RATING_RISE"   # 이달의 MVP 전용(그 달 실력 점수 상승률 1위)
    ATTENDANCE_STREAK = "ATTENDANCE_STREAK"       # 연속 참가 10 · 20 · 30 · 40 · 50회(일정마감 때, 참석 명단 기준)


class InsightPhase(StrEnum):
    PRE = "PRE"
    POST = "POST"


class ArticleType(StrEnum):
    NOTICE = "NOTICE"          # 일정 없이 게시하는 운영진 안내
    PRE_MATCH = "PRE_MATCH"
    POST_MATCH = "POST_MATCH"   # 예약(현재 정책상 생성하지 않음)
    SESSION_RECAP = "SESSION_RECAP"
    MONTHLY_MVP = "MONTHLY_MVP"   # 이달의 MVP(월 마감 때 자동 작성 · 바로 게시)


class ArticleStatus(StrEnum):
    PENDING = "PENDING"        # 생성 대기/진행 중
    GENERATED = "GENERATED"    # 생성 완료, 미게시
    PUBLISHED = "PUBLISHED"
    REJECTED = "REJECTED"
    FAILED = "FAILED"
    SUPERSEDED = "SUPERSEDED"  # 재생성본이 게시되어 내려간 기존 게시본(삭제하지 않음)
