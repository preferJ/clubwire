from datetime import date, datetime
from typing import Any

from sqlalchemy import JSON, BigInteger, Boolean, Date, Double, ForeignKey, Index, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, CreatedAtMixin, Id, TimestampMixin, UtcDateTime


class OpponentTeam(TimestampMixin, Base):
    """원정팀 목록(클럽별). 원정 경기의 상대는 이 목록에서만 고른다(목록 화면의 [직접추가]로 등록)."""

    __tablename__ = "OPPONENT_TEAM"
    __table_args__ = (UniqueConstraint("CLUB_ID", "NAME"),)

    opponent_id: Mapped[int] = mapped_column("OPPONENT_ID", Id, primary_key=True, autoincrement=True)
    club_id: Mapped[int] = mapped_column("CLUB_ID", ForeignKey("CLUB.CLUB_ID"), nullable=False)
    name: Mapped[str] = mapped_column("NAME", String(50), nullable=False)
    active_yn: Mapped[bool] = mapped_column("ACTIVE_YN", Boolean, nullable=False, default=True)


class ClubSession(TimestampMixin, Base):
    """한 번의 모임(경기 날짜). 파이썬 클래스명은 ORM Session과 구분하려고 ClubSession."""

    __tablename__ = "SESSION"
    __table_args__ = (Index("IX_SESSION_CLUB_ID_SESSION_DATE", "CLUB_ID", "SESSION_DATE"),)

    session_id: Mapped[int] = mapped_column("SESSION_ID", Id, primary_key=True, autoincrement=True)
    club_id: Mapped[int] = mapped_column("CLUB_ID", ForeignKey("CLUB.CLUB_ID"), nullable=False)
    session_date: Mapped[date] = mapped_column("SESSION_DATE", Date, nullable=False)
    title: Mapped[str] = mapped_column("TITLE", String(100), nullable=False)
    location: Mapped[str | None] = mapped_column("LOCATION", String(200))
    status: Mapped[str] = mapped_column("STATUS", String(20), nullable=False, default="OPEN")
    team_count: Mapped[int | None] = mapped_column("TEAM_COUNT", Integer)
    confirmed_at: Mapped[datetime | None] = mapped_column("CONFIRMED_AT", UtcDateTime)
    closed_at: Mapped[datetime | None] = mapped_column("CLOSED_AT", UtcDateTime)
    deleted_at: Mapped[datetime | None] = mapped_column("DELETED_AT", UtcDateTime, comment="일정 삭제 시각(기록 보존)")
    cancelled_at: Mapped[datetime | None] = mapped_column("CANCELLED_AT", UtcDateTime)
    # 원정 경기 일정: 1팀으로 확정하면 우리 팀 + 원정팀(상대). 원정 기록은 내부 기록 · 실력 점수 · 타이틀과 완전히 분리
    away_yn: Mapped[bool] = mapped_column("AWAY_YN", Boolean, nullable=False, default=False)
    opponent_id: Mapped[int | None] = mapped_column("OPPONENT_ID", ForeignKey("OPPONENT_TEAM.OPPONENT_ID"))
    opponent_name: Mapped[str | None] = mapped_column("OPPONENT_NAME", String(50))  # 표시용(원정팀 목록 이름)
    # 일정별 공지(상시 공지와 별개). 일정 화면 · 메인 팀 편성 카드에서 팀 밸런스 안내 위에 표시
    notice: Mapped[str | None] = mapped_column("NOTICE", String(500))


class SessionMember(TimestampMixin, Base):
    """세션 참석 멤버."""

    __tablename__ = "SESSION_MEMBER"
    __table_args__ = (UniqueConstraint("SESSION_ID", "MEMBER_ID"),)

    session_member_id: Mapped[int] = mapped_column("SESSION_MEMBER_ID", Id, primary_key=True, autoincrement=True)
    session_id: Mapped[int] = mapped_column("SESSION_ID", ForeignKey("SESSION.SESSION_ID"), nullable=False)
    member_id: Mapped[int] = mapped_column("MEMBER_ID", ForeignKey("MEMBER.MEMBER_ID"), nullable=False, index=True)
    attendance_status: Mapped[str] = mapped_column("ATTENDANCE_STATUS", String(20), nullable=False, default="ATTENDING")


class SessionTeam(CreatedAtMixin, Base):
    """세션 안에서 만든 임시 팀(TEAM A/B/C). 클럽 자체가 아님."""

    __tablename__ = "SESSION_TEAM"
    __table_args__ = (UniqueConstraint("SESSION_ID", "TEAM_CODE"),)

    session_team_id: Mapped[int] = mapped_column("SESSION_TEAM_ID", Id, primary_key=True, autoincrement=True)
    session_id: Mapped[int] = mapped_column("SESSION_ID", ForeignKey("SESSION.SESSION_ID"), nullable=False)
    generation_id: Mapped[int | None] = mapped_column("GENERATION_ID", ForeignKey("TEAM_GENERATION.GENERATION_ID"))
    team_code: Mapped[str] = mapped_column("TEAM_CODE", String(5), nullable=False)
    display_name: Mapped[str] = mapped_column("DISPLAY_NAME", String(50), nullable=False)
    display_order: Mapped[int] = mapped_column("DISPLAY_ORDER", Integer, nullable=False, default=0)
    avg_rating_snapshot: Mapped[float | None] = mapped_column("AVG_RATING_SNAPSHOT", Double)
    team_strength_snapshot: Mapped[float | None] = mapped_column("TEAM_STRENGTH_SNAPSHOT", Double)
    headcount_snapshot: Mapped[int | None] = mapped_column("HEADCOUNT_SNAPSHOT", Integer)
    opponent_yn: Mapped[bool] = mapped_column("OPPONENT_YN", Boolean, nullable=False, default=False)  # 원정팀(선수 없음)


class SessionGuest(TimestampMixin, Base):
    """게스트(용병). 인원수에만 포함되고 Rating/통계는 기록하지 않는다."""

    __tablename__ = "SESSION_GUEST"

    guest_id: Mapped[int] = mapped_column("GUEST_ID", Id, primary_key=True, autoincrement=True)
    session_id: Mapped[int] = mapped_column("SESSION_ID", ForeignKey("SESSION.SESSION_ID"), nullable=False, index=True)
    guest_name: Mapped[str] = mapped_column("GUEST_NAME", String(50), nullable=False)
    session_team_id: Mapped[int | None] = mapped_column("SESSION_TEAM_ID", ForeignKey("SESSION_TEAM.SESSION_TEAM_ID"))
    active_yn: Mapped[bool] = mapped_column("ACTIVE_YN", Boolean, nullable=False, default=True)


class SessionTeamMember(TimestampMixin, Base):
    """세션 팀 배정. 팀 확정 당시 Rating/Confidence Snapshot을 보존한다.

    한 세션에서 멤버는 한 팀에만 속한다(UNIQUE SESSION_ID+MEMBER_ID).
    수동 이동은 SESSION_TEAM_ID를 바꾸고 TEAM_ASSIGNMENT_LOG에 이력을 남긴다.
    """

    __tablename__ = "SESSION_TEAM_MEMBER"
    __table_args__ = (UniqueConstraint("SESSION_ID", "MEMBER_ID"),)

    session_team_member_id: Mapped[int] = mapped_column(
        "SESSION_TEAM_MEMBER_ID", Id, primary_key=True, autoincrement=True
    )
    session_id: Mapped[int] = mapped_column("SESSION_ID", ForeignKey("SESSION.SESSION_ID"), nullable=False)
    session_team_id: Mapped[int] = mapped_column(
        "SESSION_TEAM_ID", ForeignKey("SESSION_TEAM.SESSION_TEAM_ID"), nullable=False, index=True
    )
    member_id: Mapped[int] = mapped_column("MEMBER_ID", ForeignKey("MEMBER.MEMBER_ID"), nullable=False, index=True)
    rating_snapshot: Mapped[float] = mapped_column("RATING_SNAPSHOT", Double, nullable=False)
    confidence_snapshot: Mapped[float] = mapped_column("CONFIDENCE_SNAPSHOT", Double, nullable=False)
    assign_type: Mapped[str] = mapped_column("ASSIGN_TYPE", String(10), nullable=False, default="AUTO")
    active_yn: Mapped[bool] = mapped_column("ACTIVE_YN", Boolean, nullable=False, default=True)


class TeamGeneration(CreatedAtMixin, Base):
    """팀 자동 편성 실행 이력. '왜 그날 이런 팀이 나왔는가'를 재현하기 위한 Snapshot."""

    __tablename__ = "TEAM_GENERATION"

    generation_id: Mapped[int] = mapped_column("GENERATION_ID", Id, primary_key=True, autoincrement=True)
    session_id: Mapped[int] = mapped_column("SESSION_ID", ForeignKey("SESSION.SESSION_ID"), nullable=False, index=True)
    status: Mapped[str] = mapped_column("STATUS", String(20), nullable=False, default="PREVIEW")
    team_count: Mapped[int] = mapped_column("TEAM_COUNT", Integer, nullable=False)
    attendee_count: Mapped[int] = mapped_column("ATTENDEE_COUNT", Integer, nullable=False)
    guest_count: Mapped[int] = mapped_column("GUEST_COUNT", Integer, nullable=False, default=0)
    algorithm_version: Mapped[str] = mapped_column("ALGORITHM_VERSION", String(50), nullable=False)
    config_version: Mapped[int] = mapped_column("CONFIG_VERSION", Integer, nullable=False)
    config_snapshot_json: Mapped[dict[str, Any]] = mapped_column("CONFIG_SNAPSHOT_JSON", JSON, nullable=False)
    random_seed: Mapped[int] = mapped_column("RANDOM_SEED", BigInteger, nullable=False)
    candidate_count: Mapped[int] = mapped_column("CANDIDATE_COUNT", Integer, nullable=False)
    valid_candidate_count: Mapped[int] = mapped_column("VALID_CANDIDATE_COUNT", Integer, nullable=False)
    tolerance_fallback_yn: Mapped[bool] = mapped_column("TOLERANCE_FALLBACK_YN", Boolean, nullable=False, default=False)
    spread_percent: Mapped[float] = mapped_column("SPREAD_PERCENT", Double, nullable=False)
    pair_penalty: Mapped[float] = mapped_column("PAIR_PENALTY", Double, nullable=False)
    result_json: Mapped[dict[str, Any]] = mapped_column("RESULT_JSON", JSON, nullable=False)
    confirmed_at: Mapped[datetime | None] = mapped_column("CONFIRMED_AT", UtcDateTime)


class TeamAssignmentLog(CreatedAtMixin, Base):
    """팀 확정 후 수동 변경(지각 추가, 이동, 제외) 이력."""

    __tablename__ = "TEAM_ASSIGNMENT_LOG"

    log_id: Mapped[int] = mapped_column("LOG_ID", Id, primary_key=True, autoincrement=True)
    session_id: Mapped[int] = mapped_column("SESSION_ID", ForeignKey("SESSION.SESSION_ID"), nullable=False, index=True)
    action: Mapped[str] = mapped_column("ACTION", String(10), nullable=False)
    member_id: Mapped[int | None] = mapped_column("MEMBER_ID", ForeignKey("MEMBER.MEMBER_ID"))
    guest_id: Mapped[int | None] = mapped_column("GUEST_ID", ForeignKey("SESSION_GUEST.GUEST_ID"))
    from_team_id: Mapped[int | None] = mapped_column("FROM_TEAM_ID", ForeignKey("SESSION_TEAM.SESSION_TEAM_ID"))
    to_team_id: Mapped[int | None] = mapped_column("TO_TEAM_ID", ForeignKey("SESSION_TEAM.SESSION_TEAM_ID"))
    reason: Mapped[str | None] = mapped_column("REASON", String(200))
    admin_id: Mapped[int | None] = mapped_column("ADMIN_ID", ForeignKey("CLUB_ADMIN.ADMIN_ID"))
