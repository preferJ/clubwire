from datetime import date, datetime
from typing import Any

from sqlalchemy import JSON, BigInteger, Boolean, Date, Double, ForeignKey, Index, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.timeutil import utcnow
from app.models.base import Base, CreatedAtMixin, Id, UtcDateTime


class PlayerRating(Base):
    """현재 Rating 상태(파생). Confidence는 저장하지 않고 원천값(경기 수, 마지막 출전일)으로 계산한다."""

    __tablename__ = "PLAYER_RATING"

    member_id: Mapped[int] = mapped_column("MEMBER_ID", ForeignKey("MEMBER.MEMBER_ID"), primary_key=True)
    club_id: Mapped[int] = mapped_column("CLUB_ID", ForeignKey("CLUB.CLUB_ID"), nullable=False, index=True)
    current_rating: Mapped[float] = mapped_column("CURRENT_RATING", Double, nullable=False)
    match_sample_count: Mapped[int] = mapped_column("MATCH_SAMPLE_COUNT", Integer, nullable=False, default=0)
    last_played_date: Mapped[date | None] = mapped_column("LAST_PLAYED_DATE", Date)
    updated_at: Mapped[datetime] = mapped_column(
        "UPDATED_AT", UtcDateTime, nullable=False, default=utcnow, onupdate=utcnow
    )


class PlayerRatingHistory(CreatedAtMixin, Base):
    """Rating 변경 이력(감사용으로 보존).

    재계산 시 기존 행은 지우지 않고 VOIDED_YN=true로 무효화한 뒤 새 행을 쌓는다.
    """

    __tablename__ = "PLAYER_RATING_HISTORY"
    __table_args__ = (
        Index("IX_PLAYER_RATING_HISTORY_MEMBER_ID_CREATED_AT", "MEMBER_ID", "CREATED_AT"),
        Index("IX_PLAYER_RATING_HISTORY_REF", "REFERENCE_TYPE", "REFERENCE_ID"),
        Index("IX_PLAYER_RATING_HISTORY_CLUB_ID_VOIDED_YN", "CLUB_ID", "VOIDED_YN"),
    )

    rating_history_id: Mapped[int] = mapped_column("RATING_HISTORY_ID", Id, primary_key=True, autoincrement=True)
    club_id: Mapped[int] = mapped_column("CLUB_ID", ForeignKey("CLUB.CLUB_ID"), nullable=False)
    member_id: Mapped[int] = mapped_column("MEMBER_ID", ForeignKey("MEMBER.MEMBER_ID"), nullable=False)
    before_rating: Mapped[float] = mapped_column("BEFORE_RATING", Double, nullable=False)
    after_rating: Mapped[float] = mapped_column("AFTER_RATING", Double, nullable=False)
    before_confidence: Mapped[float] = mapped_column("BEFORE_CONFIDENCE", Double, nullable=False)
    after_confidence: Mapped[float] = mapped_column("AFTER_CONFIDENCE", Double, nullable=False)
    change_amount: Mapped[float] = mapped_column("CHANGE_AMOUNT", Double, nullable=False)
    change_reason: Mapped[str] = mapped_column("CHANGE_REASON", String(30), nullable=False)
    reference_type: Mapped[str | None] = mapped_column("REFERENCE_TYPE", String(20))
    reference_id: Mapped[int | None] = mapped_column("REFERENCE_ID", BigInteger)
    algorithm_version: Mapped[str] = mapped_column("ALGORITHM_VERSION", String(50), nullable=False)
    config_version: Mapped[int] = mapped_column("CONFIG_VERSION", Integer, nullable=False)
    calc_detail_json: Mapped[dict[str, Any] | None] = mapped_column("CALC_DETAIL_JSON", JSON)
    voided_yn: Mapped[bool] = mapped_column("VOIDED_YN", Boolean, nullable=False, default=False)
    voided_at: Mapped[datetime | None] = mapped_column("VOIDED_AT", UtcDateTime)
