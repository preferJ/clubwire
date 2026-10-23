from datetime import date, datetime

from sqlalchemy import Boolean, Date, Double, ForeignKey, Index, Integer, SmallInteger, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, Id, TimestampMixin, UtcDateTime
from app.core.timeutil import utcnow


class Club(TimestampMixin, Base):
    """서비스에 등록된 스포츠팀(최상위 tenant)."""

    __tablename__ = "CLUB"

    club_id: Mapped[int] = mapped_column("CLUB_ID", Id, primary_key=True, autoincrement=True)
    club_slug: Mapped[str] = mapped_column("CLUB_SLUG", String(50), nullable=False, unique=True)
    club_name: Mapped[str] = mapped_column("CLUB_NAME", String(100), nullable=False)
    sport_type: Mapped[str] = mapped_column("SPORT_TYPE", String(20), nullable=False, default="FUTSAL")
    timezone: Mapped[str] = mapped_column("TIMEZONE", String(50), nullable=False, default="Asia/Seoul")
    config_version: Mapped[int] = mapped_column("CONFIG_VERSION", Integer, nullable=False, default=1)
    active_yn: Mapped[bool] = mapped_column("ACTIVE_YN", Boolean, nullable=False, default=True)


class ClubAdmin(TimestampMixin, Base):
    """클럽 관리자 PIN. 회원 로그인(카카오 등)은 추후 별도 USER 테이블로 확장."""

    __tablename__ = "CLUB_ADMIN"

    admin_id: Mapped[int] = mapped_column("ADMIN_ID", Id, primary_key=True, autoincrement=True)
    club_id: Mapped[int] = mapped_column("CLUB_ID", ForeignKey("CLUB.CLUB_ID"), nullable=False, index=True)
    admin_name: Mapped[str | None] = mapped_column("ADMIN_NAME", String(50))
    password_hash: Mapped[str] = mapped_column("PASSWORD_HASH", String(255), nullable=False)
    active_yn: Mapped[bool] = mapped_column("ACTIVE_YN", Boolean, nullable=False, default=True)
    last_login_at: Mapped[datetime | None] = mapped_column("LAST_LOGIN_AT", UtcDateTime)


class Member(TimestampMixin, Base):
    """실제로 경기하는 구성원. 삭제하지 않고 ACTIVE_YN=false로 비활성화."""

    __tablename__ = "MEMBER"
    __table_args__ = (Index("IX_MEMBER_CLUB_ID_ACTIVE_YN", "CLUB_ID", "ACTIVE_YN"),)

    member_id: Mapped[int] = mapped_column("MEMBER_ID", Id, primary_key=True, autoincrement=True)
    club_id: Mapped[int] = mapped_column("CLUB_ID", ForeignKey("CLUB.CLUB_ID"), nullable=False)
    name: Mapped[str] = mapped_column("NAME", String(50), nullable=False)
    profile_image_url: Mapped[str | None] = mapped_column("PROFILE_IMAGE_URL", String(500))
    display_order: Mapped[int | None] = mapped_column("DISPLAY_ORDER", Integer)
    active_yn: Mapped[bool] = mapped_column("ACTIVE_YN", Boolean, nullable=False, default=True)
    joined_at: Mapped[date | None] = mapped_column("JOINED_AT", Date)
    birth_year: Mapped[int | None] = mapped_column("BIRTH_YEAR", SmallInteger)
    # 시작 Rating(이관·수동 지정). NULL이면 클럽 설정 INITIAL_RATING에서 시작. 재계산(rebuild)도 이 값에서 출발한다.
    initial_rating: Mapped[float | None] = mapped_column("INITIAL_RATING", Double)


class SystemConfig(Base):
    """클럽별 운영 설정값. 키 정의는 app/core/club_config.py."""

    __tablename__ = "SYSTEM_CONFIG"

    club_id: Mapped[int] = mapped_column("CLUB_ID", ForeignKey("CLUB.CLUB_ID"), primary_key=True)
    config_key: Mapped[str] = mapped_column("CONFIG_KEY", String(60), primary_key=True)
    config_value: Mapped[str] = mapped_column("CONFIG_VALUE", String(200), nullable=False)
    value_type: Mapped[str] = mapped_column("VALUE_TYPE", String(10), nullable=False)
    description: Mapped[str | None] = mapped_column("DESCRIPTION", String(300))
    updated_at: Mapped[datetime] = mapped_column(
        "UPDATED_AT", UtcDateTime, nullable=False, default=utcnow, onupdate=utcnow
    )


class SystemConfigHistory(Base):
    __tablename__ = "SYSTEM_CONFIG_HISTORY"
    __table_args__ = (Index("IX_SYSTEM_CONFIG_HISTORY_CLUB_ID_CHANGED_AT", "CLUB_ID", "CHANGED_AT"),)

    history_id: Mapped[int] = mapped_column("HISTORY_ID", Id, primary_key=True, autoincrement=True)
    club_id: Mapped[int] = mapped_column("CLUB_ID", ForeignKey("CLUB.CLUB_ID"), nullable=False)
    config_key: Mapped[str] = mapped_column("CONFIG_KEY", String(60), nullable=False)
    before_value: Mapped[str | None] = mapped_column("BEFORE_VALUE", String(200))
    after_value: Mapped[str] = mapped_column("AFTER_VALUE", String(200), nullable=False)
    config_version: Mapped[int] = mapped_column("CONFIG_VERSION", Integer, nullable=False)
    changed_by_admin_id: Mapped[int | None] = mapped_column("CHANGED_BY_ADMIN_ID", ForeignKey("CLUB_ADMIN.ADMIN_ID"))
    changed_at: Mapped[datetime] = mapped_column("CHANGED_AT", UtcDateTime, nullable=False, default=utcnow)
