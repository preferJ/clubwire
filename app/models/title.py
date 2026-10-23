from datetime import date, datetime
from typing import Any

from sqlalchemy import JSON, Boolean, Date, ForeignKey, Index, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, CreatedAtMixin, Id, TimestampMixin, UtcDateTime


class TitleType(TimestampMixin, Base):
    """클럽이 운영하는 타이틀 정의(이주의 득점왕 · 도움왕, 이달의 MVP …).

    AWARD_METHOD=MANUAL : 관리자가 수여
    AWARD_METHOD=AUTO   : 주간 타이틀은 [일정마감] 시 AUTO_RULE로 자동 집계(주 단위 재계산),
                          이달의 MVP(MONTHLY)는 월 마감 때 실력 점수 상승률 1위(app/services/mvp_service.py)
    """

    __tablename__ = "TITLE_TYPE"
    __table_args__ = (UniqueConstraint("CLUB_ID", "TITLE_CODE"),)

    title_type_id: Mapped[int] = mapped_column("TITLE_TYPE_ID", Id, primary_key=True, autoincrement=True)
    club_id: Mapped[int] = mapped_column("CLUB_ID", ForeignKey("CLUB.CLUB_ID"), nullable=False)
    title_code: Mapped[str] = mapped_column("TITLE_CODE", String(30), nullable=False)
    title_name: Mapped[str] = mapped_column("TITLE_NAME", String(50), nullable=False)
    period_type: Mapped[str] = mapped_column("PERIOD_TYPE", String(10), nullable=False, default="WEEKLY")
    award_method: Mapped[str] = mapped_column("AWARD_METHOD", String(10), nullable=False, default="MANUAL")
    auto_rule: Mapped[str | None] = mapped_column("AUTO_RULE", String(30))
    counts_as_mvp_yn: Mapped[bool] = mapped_column("COUNTS_AS_MVP_YN", Boolean, nullable=False, default=False)
    active_yn: Mapped[bool] = mapped_column("ACTIVE_YN", Boolean, nullable=False, default=True)
    display_order: Mapped[int] = mapped_column("DISPLAY_ORDER", Integer, nullable=False, default=0)


class MemberTitle(CreatedAtMixin, Base):
    """타이틀 수여 이력(이달의 MVP 포함). 취소는 CANCELLED_YN."""

    __tablename__ = "MEMBER_TITLE"
    __table_args__ = (
        Index("IX_MEMBER_TITLE_CLUB_ID_PERIOD_START", "CLUB_ID", "PERIOD_START"),
        Index("IX_MEMBER_TITLE_TITLE_TYPE_ID_PERIOD_START", "TITLE_TYPE_ID", "PERIOD_START"),
    )

    member_title_id: Mapped[int] = mapped_column("MEMBER_TITLE_ID", Id, primary_key=True, autoincrement=True)
    club_id: Mapped[int] = mapped_column("CLUB_ID", ForeignKey("CLUB.CLUB_ID"), nullable=False)
    title_type_id: Mapped[int] = mapped_column("TITLE_TYPE_ID", ForeignKey("TITLE_TYPE.TITLE_TYPE_ID"), nullable=False)
    member_id: Mapped[int] = mapped_column("MEMBER_ID", ForeignKey("MEMBER.MEMBER_ID"), nullable=False, index=True)
    period_start: Mapped[date] = mapped_column("PERIOD_START", Date, nullable=False)
    period_end: Mapped[date] = mapped_column("PERIOD_END", Date, nullable=False)
    session_id: Mapped[int | None] = mapped_column("SESSION_ID", ForeignKey("SESSION.SESSION_ID"))
    award_method: Mapped[str] = mapped_column("AWARD_METHOD", String(10), nullable=False)
    facts_json: Mapped[dict[str, Any] | None] = mapped_column("FACTS_JSON", JSON)
    note: Mapped[str | None] = mapped_column("NOTE", String(200))
    cancelled_yn: Mapped[bool] = mapped_column("CANCELLED_YN", Boolean, nullable=False, default=False)
    cancelled_at: Mapped[datetime | None] = mapped_column("CANCELLED_AT", UtcDateTime)
    admin_id: Mapped[int | None] = mapped_column("ADMIN_ID", ForeignKey("CLUB_ADMIN.ADMIN_ID"))
