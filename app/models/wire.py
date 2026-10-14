"""The Wire: Insight / AI Article."""
from datetime import datetime
from typing import Any

from sqlalchemy import JSON, Boolean, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.timeutil import utcnow
from app.models.base import Base, CreatedAtMixin, Id, TimestampMixin, UtcDateTime


class InsightTypeConfig(TimestampMixin, Base):
    """Insight Type별 사용 여부/중요도 범위/태그. (전역 공통)"""

    __tablename__ = "INSIGHT_TYPE_CONFIG"

    insight_type: Mapped[str] = mapped_column("INSIGHT_TYPE", String(40), primary_key=True)
    category: Mapped[str] = mapped_column("CATEGORY", String(30), nullable=False)
    enabled_yn: Mapped[bool] = mapped_column("ENABLED_YN", Boolean, nullable=False, default=True)
    base_importance: Mapped[int] = mapped_column("BASE_IMPORTANCE", Integer, nullable=False)
    min_importance: Mapped[int] = mapped_column("MIN_IMPORTANCE", Integer, nullable=False, default=0)
    max_importance: Mapped[int] = mapped_column("MAX_IMPORTANCE", Integer, nullable=False, default=100)
    pre_match_yn: Mapped[bool] = mapped_column("PRE_MATCH_YN", Boolean, nullable=False, default=False)
    post_match_yn: Mapped[bool] = mapped_column("POST_MATCH_YN", Boolean, nullable=False, default=False)
    tag_name: Mapped[str | None] = mapped_column("TAG_NAME", String(30))
    rule_version: Mapped[str] = mapped_column("RULE_VERSION", String(40), nullable=False)
    description: Mapped[str | None] = mapped_column("DESCRIPTION", String(300))


class InsightConfigParam(Base):
    __tablename__ = "INSIGHT_CONFIG_PARAM"

    insight_type: Mapped[str] = mapped_column(
        "INSIGHT_TYPE", ForeignKey("INSIGHT_TYPE_CONFIG.INSIGHT_TYPE"), primary_key=True
    )
    param_key: Mapped[str] = mapped_column("PARAM_KEY", String(50), primary_key=True)
    param_value: Mapped[str] = mapped_column("PARAM_VALUE", String(200), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        "UPDATED_AT", UtcDateTime, nullable=False, default=utcnow, onupdate=utcnow
    )


class Insight(CreatedAtMixin, Base):
    """Backend가 원본 데이터에서 계산해 발견한 구조화된 사건. AI 문장이 아니다.

    재생성 시 기존 행은 ACTIVE_YN=false (기사 근거 보존을 위해 삭제하지 않음).
    """

    __tablename__ = "INSIGHT"
    __table_args__ = (
        Index("IX_INSIGHT_SESSION_ID_INSIGHT_TYPE", "SESSION_ID", "INSIGHT_TYPE"),
        Index("IX_INSIGHT_CLUB_ID_CREATED_AT", "CLUB_ID", "CREATED_AT"),
    )

    insight_id: Mapped[int] = mapped_column("INSIGHT_ID", Id, primary_key=True, autoincrement=True)
    club_id: Mapped[int] = mapped_column("CLUB_ID", ForeignKey("CLUB.CLUB_ID"), nullable=False)
    session_id: Mapped[int | None] = mapped_column("SESSION_ID", ForeignKey("SESSION.SESSION_ID"))
    match_id: Mapped[int | None] = mapped_column("MATCH_ID", ForeignKey("MATCH_GAME.MATCH_ID"))
    member_id: Mapped[int | None] = mapped_column("MEMBER_ID", ForeignKey("MEMBER.MEMBER_ID"))
    insight_type: Mapped[str] = mapped_column(
        "INSIGHT_TYPE", ForeignKey("INSIGHT_TYPE_CONFIG.INSIGHT_TYPE"), nullable=False
    )
    category: Mapped[str] = mapped_column("CATEGORY", String(30), nullable=False)
    phase: Mapped[str] = mapped_column("PHASE", String(10), nullable=False)
    importance: Mapped[int] = mapped_column("IMPORTANCE", Integer, nullable=False)
    facts_json: Mapped[dict[str, Any]] = mapped_column("FACTS_JSON", JSON, nullable=False)
    rule_version: Mapped[str] = mapped_column("RULE_VERSION", String(40), nullable=False)
    active_yn: Mapped[bool] = mapped_column("ACTIVE_YN", Boolean, nullable=False, default=True)


class InsightMember(Base):
    """Insight에 등장하는 멤버(RARE_PAIR처럼 2명 이상인 경우, 멤버별 기사 조회용)."""

    __tablename__ = "INSIGHT_MEMBER"

    insight_id: Mapped[int] = mapped_column("INSIGHT_ID", ForeignKey("INSIGHT.INSIGHT_ID"), primary_key=True)
    member_id: Mapped[int] = mapped_column("MEMBER_ID", ForeignKey("MEMBER.MEMBER_ID"), primary_key=True, index=True)
    role: Mapped[str] = mapped_column("ROLE", String(20), nullable=False, default="SUBJECT")


class AiArticle(TimestampMixin, Base):
    """AI 기사. 재생성은 새 행(PARENT_ARTICLE_ID, GENERATION_NO)으로 쌓고 기존 행은 보존."""

    __tablename__ = "AI_ARTICLE"
    __table_args__ = (
        Index("IX_AI_ARTICLE_CLUB_ID_CREATED_AT", "CLUB_ID", "CREATED_AT"),
        Index("IX_AI_ARTICLE_CLUB_ID_PUBLISHED_YN_PUBLISHED_AT", "CLUB_ID", "PUBLISHED_YN", "PUBLISHED_AT"),
    )

    article_id: Mapped[int] = mapped_column("ARTICLE_ID", Id, primary_key=True, autoincrement=True)
    club_id: Mapped[int] = mapped_column("CLUB_ID", ForeignKey("CLUB.CLUB_ID"), nullable=False)
    session_id: Mapped[int | None] = mapped_column("SESSION_ID", ForeignKey("SESSION.SESSION_ID"), index=True)
    match_id: Mapped[int | None] = mapped_column("MATCH_ID", ForeignKey("MATCH_GAME.MATCH_ID"))
    article_type: Mapped[str] = mapped_column("ARTICLE_TYPE", String(20), nullable=False)
    title: Mapped[str | None] = mapped_column("TITLE", String(200))
    summary: Mapped[str | None] = mapped_column("SUMMARY", String(500))
    content: Mapped[str | None] = mapped_column("CONTENT", Text)
    model_name: Mapped[str] = mapped_column("MODEL_NAME", String(100), nullable=False)
    prompt_version: Mapped[str] = mapped_column("PROMPT_VERSION", String(40), nullable=False)
    insight_rule_version: Mapped[str | None] = mapped_column("INSIGHT_RULE_VERSION", String(1000))
    status: Mapped[str] = mapped_column("STATUS", String(20), nullable=False, default="PENDING")
    published_yn: Mapped[bool] = mapped_column("PUBLISHED_YN", Boolean, nullable=False, default=False)
    published_at: Mapped[datetime | None] = mapped_column("PUBLISHED_AT", UtcDateTime)
    parent_article_id: Mapped[int | None] = mapped_column("PARENT_ARTICLE_ID", ForeignKey("AI_ARTICLE.ARTICLE_ID"))
    generation_no: Mapped[int] = mapped_column("GENERATION_NO", Integer, nullable=False, default=1)
    request_json: Mapped[dict[str, Any] | None] = mapped_column("REQUEST_JSON", JSON)
    response_json: Mapped[dict[str, Any] | None] = mapped_column("RESPONSE_JSON", JSON)
    error_message: Mapped[str | None] = mapped_column("ERROR_MESSAGE", Text)


class AiArticleInsight(Base):
    """기사가 실제로 사용한 Insight(AI 응답 usedInsightIds)."""

    __tablename__ = "AI_ARTICLE_INSIGHT"

    article_id: Mapped[int] = mapped_column("ARTICLE_ID", ForeignKey("AI_ARTICLE.ARTICLE_ID"), primary_key=True)
    insight_id: Mapped[int] = mapped_column("INSIGHT_ID", ForeignKey("INSIGHT.INSIGHT_ID"), primary_key=True)


class ArticleTag(Base):
    """기사 태그. AI가 만들지 않고 Insight Type → Canonical Tag 매핑으로 Backend가 붙인다."""

    __tablename__ = "ARTICLE_TAG"

    article_id: Mapped[int] = mapped_column("ARTICLE_ID", ForeignKey("AI_ARTICLE.ARTICLE_ID"), primary_key=True)
    tag_name: Mapped[str] = mapped_column("TAG_NAME", String(30), primary_key=True, index=True)
