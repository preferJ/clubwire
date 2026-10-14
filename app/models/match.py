from datetime import datetime

from sqlalchemy import Boolean, Double, ForeignKey, Index, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, CreatedAtMixin, Id, TimestampMixin, UtcDateTime


class MatchGame(TimestampMixin, Base):
    """실제 한 경기.

    - 경기 일정은 미리 만들지 않는다. '다음 경기'를 그때그때 1건씩 만들고 GAME_NO만 증가.
    - 대진(TEAM_A/B)은 매 경기 관리자가 지정한다.
    - 타이머 원본: STARTED_AT / PAUSED_AT / PAUSED_SECONDS / GAME_DURATION_SEC (매초 기록하지 않음)
    - FINISHED(경기 종료)와 FINALIZED_AT(기록 확정 → 파생 데이터 반영)을 구분한다.
    - SCORE는 GOAL 이벤트와 같은 트랜잭션에서만 바뀐다. VERSION은 변경마다 +1.
    """

    __tablename__ = "MATCH_GAME"
    __table_args__ = (UniqueConstraint("SESSION_ID", "GAME_NO"),)

    match_id: Mapped[int] = mapped_column("MATCH_ID", Id, primary_key=True, autoincrement=True)
    session_id: Mapped[int] = mapped_column("SESSION_ID", ForeignKey("SESSION.SESSION_ID"), nullable=False)
    game_no: Mapped[int] = mapped_column("GAME_NO", Integer, nullable=False)
    team_a_id: Mapped[int] = mapped_column("TEAM_A_ID", ForeignKey("SESSION_TEAM.SESSION_TEAM_ID"), nullable=False)
    team_b_id: Mapped[int] = mapped_column("TEAM_B_ID", ForeignKey("SESSION_TEAM.SESSION_TEAM_ID"), nullable=False)
    score_a: Mapped[int] = mapped_column("SCORE_A", Integer, nullable=False, default=0)
    score_b: Mapped[int] = mapped_column("SCORE_B", Integer, nullable=False, default=0)
    game_status: Mapped[str] = mapped_column("GAME_STATUS", String(20), nullable=False, default="READY")

    # 경기 규칙 Snapshot (생성 시점 설정값)
    game_duration_sec: Mapped[int] = mapped_column("GAME_DURATION_SEC", Integer, nullable=False)
    auto_end_yn: Mapped[bool] = mapped_column("AUTO_END_YN", Boolean, nullable=False, default=True)
    early_end_goals: Mapped[int | None] = mapped_column("EARLY_END_GOALS", Integer)

    started_at: Mapped[datetime | None] = mapped_column("STARTED_AT", UtcDateTime)
    paused_at: Mapped[datetime | None] = mapped_column("PAUSED_AT", UtcDateTime)
    paused_seconds: Mapped[float] = mapped_column("PAUSED_SECONDS", Double, nullable=False, default=0.0)
    finished_at: Mapped[datetime | None] = mapped_column("FINISHED_AT", UtcDateTime)
    end_reason: Mapped[str | None] = mapped_column("END_REASON", String(20))
    finalized_at: Mapped[datetime | None] = mapped_column("FINALIZED_AT", UtcDateTime)
    win_team_id: Mapped[int | None] = mapped_column("WIN_TEAM_ID", ForeignKey("SESSION_TEAM.SESSION_TEAM_ID"))

    # 경기 시작 시점 전력 Snapshot (이변/접전 판단용, 사용자에게 숫자 노출 안 함)
    team_a_headcount: Mapped[int | None] = mapped_column("TEAM_A_HEADCOUNT", Integer)
    team_b_headcount: Mapped[int | None] = mapped_column("TEAM_B_HEADCOUNT", Integer)
    team_a_strength: Mapped[float | None] = mapped_column("TEAM_A_STRENGTH", Double)
    team_b_strength: Mapped[float | None] = mapped_column("TEAM_B_STRENGTH", Double)
    expected_a: Mapped[float | None] = mapped_column("EXPECTED_A", Double)

    version: Mapped[int] = mapped_column("VERSION", Integer, nullable=False, default=0)


class MatchMember(CreatedAtMixin, Base):
    """해당 경기에 실제로 뛴 멤버(경기 시작 시 팀 명단에서 생성, 이후 결장/추가 수정 가능)."""

    __tablename__ = "MATCH_MEMBER"
    __table_args__ = (UniqueConstraint("MATCH_ID", "MEMBER_ID"),)

    match_member_id: Mapped[int] = mapped_column("MATCH_MEMBER_ID", Id, primary_key=True, autoincrement=True)
    match_id: Mapped[int] = mapped_column("MATCH_ID", ForeignKey("MATCH_GAME.MATCH_ID"), nullable=False)
    member_id: Mapped[int] = mapped_column("MEMBER_ID", ForeignKey("MEMBER.MEMBER_ID"), nullable=False, index=True)
    session_team_id: Mapped[int] = mapped_column(
        "SESSION_TEAM_ID", ForeignKey("SESSION_TEAM.SESSION_TEAM_ID"), nullable=False
    )


class MatchEvent(CreatedAtMixin, Base):
    """경기 이벤트 타임라인. 삭제하지 않는다(골 취소 = CANCELLED_YN + GOAL_CANCEL 이벤트).

    GOAL:
      TEAM_ID        = 점수를 얻은 팀
      SCORER_MEMBER_ID = 득점자(자책골이면 자책한 선수, 게스트 득점이면 NULL)
      OWN_GOAL_YN / GUEST_GOAL_YN
    """

    __tablename__ = "MATCH_EVENT"
    __table_args__ = (
        UniqueConstraint("MATCH_ID", "IDEMPOTENCY_KEY"),
        Index("IX_MATCH_EVENT_MATCH_ID_CREATED_AT", "MATCH_ID", "CREATED_AT"),
    )

    event_id: Mapped[int] = mapped_column("EVENT_ID", Id, primary_key=True, autoincrement=True)
    match_id: Mapped[int] = mapped_column("MATCH_ID", ForeignKey("MATCH_GAME.MATCH_ID"), nullable=False)
    event_type: Mapped[str] = mapped_column("EVENT_TYPE", String(20), nullable=False)
    team_id: Mapped[int | None] = mapped_column("TEAM_ID", ForeignKey("SESSION_TEAM.SESSION_TEAM_ID"))
    scorer_member_id: Mapped[int | None] = mapped_column(
        "SCORER_MEMBER_ID", ForeignKey("MEMBER.MEMBER_ID"), index=True
    )
    assist_member_id: Mapped[int | None] = mapped_column(
        "ASSIST_MEMBER_ID", ForeignKey("MEMBER.MEMBER_ID"), index=True
    )
    member_id: Mapped[int | None] = mapped_column("MEMBER_ID", ForeignKey("MEMBER.MEMBER_ID"))  # 출전 명단 변경 대상
    own_goal_yn: Mapped[bool] = mapped_column("OWN_GOAL_YN", Boolean, nullable=False, default=False)
    guest_goal_yn: Mapped[bool] = mapped_column("GUEST_GOAL_YN", Boolean, nullable=False, default=False)
    elapsed_sec: Mapped[int | None] = mapped_column("ELAPSED_SEC", Integer)
    remaining_sec: Mapped[int | None] = mapped_column("REMAINING_SEC", Integer)
    ref_event_id: Mapped[int | None] = mapped_column("REF_EVENT_ID", ForeignKey("MATCH_EVENT.EVENT_ID"))
    cancelled_yn: Mapped[bool] = mapped_column("CANCELLED_YN", Boolean, nullable=False, default=False)
    idempotency_key: Mapped[str | None] = mapped_column("IDEMPOTENCY_KEY", String(64))
    memo: Mapped[str | None] = mapped_column("MEMO", String(200))
    admin_id: Mapped[int | None] = mapped_column("ADMIN_ID", ForeignKey("CLUB_ADMIN.ADMIN_ID"))
