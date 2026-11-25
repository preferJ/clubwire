"""카카오 계정과 클럽 선수 연결. 로그인과 선수 본인 확인(관리자 승인)을 분리한다."""
from datetime import datetime

from sqlalchemy import Boolean, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, Id, TimestampMixin, UtcDateTime


class AppUser(TimestampMixin, Base):
    __tablename__ = "APP_USER"

    user_id: Mapped[int] = mapped_column("USER_ID", Id, primary_key=True, autoincrement=True)
    kakao_id: Mapped[str] = mapped_column("KAKAO_ID", String(40), nullable=False, unique=True)
    nickname: Mapped[str] = mapped_column("NICKNAME", String(100), nullable=False)
    active_yn: Mapped[bool] = mapped_column("ACTIVE_YN", Boolean, nullable=False, default=True)
    token_version: Mapped[int] = mapped_column("TOKEN_VERSION", Integer, nullable=False, default=0)


class MemberAccountLink(TimestampMixin, Base):
    """승인된 연결만 보관. 삭제 시 즉시 권한 회수; 신청/승인 이력은 요청 테이블에 보존."""
    __tablename__ = "MEMBER_ACCOUNT_LINK"
    __table_args__ = (UniqueConstraint("CLUB_ID", "USER_ID"), UniqueConstraint("MEMBER_ID"))

    link_id: Mapped[int] = mapped_column("LINK_ID", Id, primary_key=True, autoincrement=True)
    club_id: Mapped[int] = mapped_column("CLUB_ID", ForeignKey("CLUB.CLUB_ID"), nullable=False)
    user_id: Mapped[int] = mapped_column("USER_ID", ForeignKey("APP_USER.USER_ID"), nullable=False)
    member_id: Mapped[int] = mapped_column("MEMBER_ID", ForeignKey("MEMBER.MEMBER_ID"), nullable=False)
    approved_by_admin_id: Mapped[int] = mapped_column("APPROVED_BY_ADMIN_ID", ForeignKey("CLUB_ADMIN.ADMIN_ID"), nullable=False)
    approved_at: Mapped[datetime] = mapped_column("APPROVED_AT", UtcDateTime, nullable=False)


class MemberLinkRequest(TimestampMixin, Base):
    __tablename__ = "MEMBER_LINK_REQUEST"

    request_id: Mapped[int] = mapped_column("REQUEST_ID", Id, primary_key=True, autoincrement=True)
    club_id: Mapped[int] = mapped_column("CLUB_ID", ForeignKey("CLUB.CLUB_ID"), nullable=False, index=True)
    user_id: Mapped[int] = mapped_column("USER_ID", ForeignKey("APP_USER.USER_ID"), nullable=False, index=True)
    member_id: Mapped[int] = mapped_column("MEMBER_ID", ForeignKey("MEMBER.MEMBER_ID"), nullable=False)
    status: Mapped[str] = mapped_column("STATUS", String(12), nullable=False, default="PENDING")
    reviewed_by_admin_id: Mapped[int | None] = mapped_column("REVIEWED_BY_ADMIN_ID", ForeignKey("CLUB_ADMIN.ADMIN_ID"))
    reviewed_at: Mapped[datetime | None] = mapped_column("REVIEWED_AT", UtcDateTime)
