"""AI 기사: 생성 요청 → (백그라운드) OpenAI 호출 → 검증 → 저장/태그 → 게시."""
import logging
from typing import Any

from sqlalchemy import func, select, tuple_
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.database import SessionLocal, emit
from app.core.errors import Conflict, NotFound
from app.core.timeutil import to_iso, utcnow
from app.models import (
    AiArticle,
    AiArticleInsight,
    ArticleTag,
    Club,
    ClubSession,
    Insight,
    InsightMember,
    InsightTypeConfig,
    Member,
)
from app.models.enums import ArticleStatus, ArticleType
from app.integrations.openai.writer import PROMPT_VERSION, get_writer
from app.services.config_service import load_config
from app.services.session_service import team_rosters

log = logging.getLogger("clubwire.wire")

ARTICLE_TYPE_TAG = {ArticleType.PRE_MATCH: "프리뷰", ArticleType.SESSION_RECAP: "마감", ArticleType.POST_MATCH: "경기",
                    ArticleType.MONTHLY_MVP: "이달의 MVP"}
# 게시 설정(ARTICLE_PUBLISH_MODE)과 상관없이 생성 즉시 게시하는 기사
ALWAYS_PUBLISH = {ArticleType.MONTHLY_MVP}


def _model_for(article_type: str) -> str:
    recap = (ArticleType.SESSION_RECAP, ArticleType.MONTHLY_MVP)
    return settings.AI_RECAP_MODEL if article_type in recap else settings.AI_ARTICLE_MODEL


def build_payload(db: Session, club: Club, session: ClubSession, article_type: str, insights: list[Insight],
                  extra_context: dict[str, Any] | None = None) -> dict[str, Any]:
    """AI 전용 DTO. DB Row를 그대로 넘기지 않는다."""
    cfg = load_config(db, club.club_id)
    names = {m.member_id: m.name for m in db.scalars(select(Member).where(Member.club_id == club.club_id))}
    chosen = sorted(insights, key=lambda i: (-i.importance, i.insight_id))[: int(cfg["WIRE_MAX_INSIGHTS"])]
    payload: dict[str, Any] = {
        "articleType": article_type,
        "clubName": club.club_name,
        "sessionDate": session.session_date.isoformat(),
        "sessionTitle": session.title,
        "location": session.location,
        "insights": [
            {
                "id": i.insight_id, "type": i.insight_type, "category": i.category, "importance": i.importance,
                "subject": {"memberId": i.member_id, "name": names.get(i.member_id)} if i.member_id else None,
                "facts": i.facts_json,
            }
            for i in chosen
        ],
    }
    if article_type == ArticleType.PRE_MATCH:
        payload["teams"] = [
            {"teamCode": info["team"].team_code,
             "members": [m.name for _, m in info["members"]], "guestCount": len(info["guests"])}
            for info in team_rosters(db, session.session_id).values()
        ]
    if extra_context:
        payload.update(extra_context)
    return payload


def create_article(db: Session, club: Club, session: ClubSession, article_type: str, insights: list[Insight],
                   extra_context: dict[str, Any] | None = None) -> AiArticle:
    """PENDING 기사 행 생성(호출 측 트랜잭션). 실제 생성은 run_generation()."""
    payload = build_payload(db, club, session, article_type, insights, extra_context)
    rule_versions = sorted({f"{i.insight_type}:{i.rule_version}" for i in insights})
    provider = settings.ai_provider_resolved
    a = AiArticle(
        club_id=club.club_id, session_id=session.session_id, article_type=article_type,
        model_name=_model_for(article_type) if provider == "openai" else "stub",
        prompt_version=PROMPT_VERSION, insight_rule_version=",".join(rule_versions)[:1000] or None,
        status=ArticleStatus.PENDING, published_yn=False, generation_no=1, request_json=payload,
    )
    db.add(a)
    db.flush()
    emit(db, club.club_id, "ARTICLE_UPDATED", {"articleId": a.article_id, "status": a.status})
    return a


def run_generation(article_id: int) -> None:
    """백그라운드 실행(자체 DB 세션). 실패해도 예외를 밖으로 던지지 않고 FAILED로 남긴다."""
    with SessionLocal() as db:
        a = db.get(AiArticle, article_id)
        if not a or a.status != ArticleStatus.PENDING:
            return
        try:
            writer = get_writer()
            draft, raw = writer.write(a.request_json or {}, a.model_name)
        except Exception as e:  # noqa: BLE001
            log.exception("article generation failed: %s", article_id)
            a.status = ArticleStatus.FAILED
            a.error_message = str(e)[:4000]
            emit(db, a.club_id, "ARTICLE_UPDATED", {"articleId": a.article_id, "status": a.status})
            db.commit()
            return
        a.title, a.summary, a.content = draft.title, draft.summary, draft.body
        a.response_json = raw
        a.status = ArticleStatus.GENERATED
        a.error_message = None
        for iid in draft.usedInsightIds:
            db.add(AiArticleInsight(article_id=a.article_id, insight_id=iid))
        db.flush()
        _apply_tags(db, a)
        if a.article_type in ALWAYS_PUBLISH or load_config(db, a.club_id)["ARTICLE_PUBLISH_MODE"] == "AUTO":
            _publish(db, a)
        emit(db, a.club_id, "ARTICLE_UPDATED", {"articleId": a.article_id, "status": a.status})
        db.commit()


def _apply_tags(db: Session, a: AiArticle) -> None:
    tags = set(db.scalars(
        select(InsightTypeConfig.tag_name)
        .join(Insight, Insight.insight_type == InsightTypeConfig.insight_type)
        .join(AiArticleInsight, AiArticleInsight.insight_id == Insight.insight_id)
        .where(AiArticleInsight.article_id == a.article_id, InsightTypeConfig.tag_name.is_not(None))
    ))
    if ARTICLE_TYPE_TAG.get(a.article_type):
        tags.add(ARTICLE_TYPE_TAG[a.article_type])
    existing = set(db.scalars(select(ArticleTag.tag_name).where(ArticleTag.article_id == a.article_id)))
    for t in sorted(tags - existing):
        db.add(ArticleTag(article_id=a.article_id, tag_name=t))


def _publish(db: Session, a: AiArticle) -> None:
    # 같은 일정/같은 종류의 기존 게시본은 내리되 삭제하지 않는다(SUPERSEDED)
    for old in db.scalars(select(AiArticle).where(
            AiArticle.club_id == a.club_id, AiArticle.session_id == a.session_id,
            AiArticle.article_type == a.article_type, AiArticle.published_yn.is_(True),
            AiArticle.article_id != a.article_id)):
        old.published_yn = False
        old.status = ArticleStatus.SUPERSEDED
    a.status = ArticleStatus.PUBLISHED
    a.published_yn = True
    a.published_at = utcnow()


def _get(db: Session, club_id: int, article_id: int, lock: bool = False) -> AiArticle:
    stmt = select(AiArticle).where(AiArticle.article_id == article_id, AiArticle.club_id == club_id)
    if lock:
        stmt = stmt.with_for_update()
    a = db.scalar(stmt)
    if not a:
        raise NotFound("기사를 찾을 수 없습니다.", "ARTICLE_NOT_FOUND")
    return a


def publish_article(db: Session, club_id: int, article_id: int) -> AiArticle:
    a = _get(db, club_id, article_id, lock=True)
    if a.status not in (ArticleStatus.GENERATED, ArticleStatus.REJECTED, ArticleStatus.SUPERSEDED):
        raise Conflict(f"게시할 수 없는 상태입니다({a.status}).", "INVALID_ARTICLE_STATUS")
    _publish(db, a)
    emit(db, club_id, "ARTICLE_UPDATED", {"articleId": a.article_id, "status": a.status})
    db.commit()
    return a


def reject_article(db: Session, club_id: int, article_id: int) -> AiArticle:
    a = _get(db, club_id, article_id, lock=True)
    if a.status not in (ArticleStatus.GENERATED, ArticleStatus.PUBLISHED, ArticleStatus.FAILED):
        raise Conflict(f"내릴 수 없는 상태입니다({a.status}).", "INVALID_ARTICLE_STATUS")
    a.status = ArticleStatus.REJECTED
    a.published_yn = False
    emit(db, club_id, "ARTICLE_UPDATED", {"articleId": a.article_id, "status": a.status})
    db.commit()
    return a


def regenerate_article(db: Session, club_id: int, article_id: int) -> AiArticle:
    """같은 사실(REQUEST_JSON)로 새 버전을 만든다. 기존 기사는 그대로 둔다."""
    src = _get(db, club_id, article_id)
    if src.status == ArticleStatus.PENDING:
        raise Conflict("생성 중인 기사입니다.", "ARTICLE_PENDING")
    root_id = src.parent_article_id or src.article_id
    max_no = db.scalar(select(func.max(AiArticle.generation_no)).where(
        (AiArticle.article_id == root_id) | (AiArticle.parent_article_id == root_id))) or 1
    provider = settings.ai_provider_resolved
    a = AiArticle(
        club_id=club_id, session_id=src.session_id, match_id=src.match_id, article_type=src.article_type,
        model_name=_model_for(src.article_type) if provider == "openai" else "stub",
        prompt_version=PROMPT_VERSION, insight_rule_version=src.insight_rule_version,
        status=ArticleStatus.PENDING, published_yn=False, parent_article_id=root_id, generation_no=max_no + 1,
        request_json=src.request_json,
    )
    db.add(a)
    db.flush()
    emit(db, club_id, "ARTICLE_UPDATED", {"articleId": a.article_id, "status": a.status})
    db.commit()
    return a


# ------------------------------------------------------------------ 조회
def serialize_article(db: Session, a: AiArticle, *, detail: bool = False, admin: bool = False) -> dict:
    tags = list(db.scalars(select(ArticleTag.tag_name).where(ArticleTag.article_id == a.article_id).order_by(ArticleTag.tag_name)))
    session = db.get(ClubSession, a.session_id) if a.session_id else None  # 화면에서 일정 날짜별로 묶기용
    data = {
        "articleId": a.article_id, "articleType": a.article_type, "sessionId": a.session_id,
        "sessionDate": session.session_date.isoformat() if session else None,
        "title": a.title, "summary": a.summary, "tags": tags, "status": a.status,
        "publishedAt": to_iso(a.published_at), "createdAt": to_iso(a.created_at),
        "generationNo": a.generation_no, "parentArticleId": a.parent_article_id,
    }
    if detail:
        data["content"] = a.content
        used = list(db.scalars(select(AiArticleInsight.insight_id).where(AiArticleInsight.article_id == a.article_id)))
        data["usedInsightIds"] = used
        mids = set(db.scalars(select(InsightMember.member_id).where(InsightMember.insight_id.in_(used)))) if used else set()
        if a.article_type == ArticleType.MONTHLY_MVP:  # Insight 없이 쓰는 기사: MVP · 2·3위를 '나온 선수'로
            mvp = (a.request_json or {}).get("monthlyMvp") or {}
            mids |= {p["memberId"] for p in mvp.get("winners", []) + mvp.get("runnersUp", []) if p.get("memberId")}
        data["members"] = [{"memberId": m.member_id, "name": m.name}
                           for m in db.scalars(select(Member).where(Member.member_id.in_(mids)))] if mids else []
    if admin:
        data.update({"modelName": a.model_name, "promptVersion": a.prompt_version,
                     "insightRuleVersion": a.insight_rule_version, "errorMessage": a.error_message})
        if detail:
            data["requestJson"] = a.request_json
    return data


def list_articles(db: Session, club_id: int, *, published_only: bool = True, tag: str | None = None,
                  member_id: int | None = None, session_id: int | None = None, status: str | None = None,
                  limit: int = 20, before_id: int | None = None) -> list[AiArticle]:
    stmt = select(AiArticle).where(AiArticle.club_id == club_id)
    if published_only:
        stmt = stmt.where(AiArticle.published_yn.is_(True))
    elif status:
        stmt = stmt.where(AiArticle.status == status)
    if session_id:
        stmt = stmt.where(AiArticle.session_id == session_id)
    if tag:
        stmt = stmt.where(AiArticle.article_id.in_(select(ArticleTag.article_id).where(ArticleTag.tag_name == tag)))
    if member_id:
        stmt = stmt.where(AiArticle.article_id.in_(
            select(AiArticleInsight.article_id)
            .join(InsightMember, InsightMember.insight_id == AiArticleInsight.insight_id)
            .where(InsightMember.member_id == member_id)))
    if before_id:
        # 커서는 정렬 기준과 같아야 한다: 게시본은 (PUBLISHED_AT, ARTICLE_ID), 관리자 전체는 ARTICLE_ID.
        # (늦게 게시된 옛 기사가 있으면 ID만으로 자를 때 그 뒤 기사가 빠진다)
        cursor = db.get(AiArticle, before_id) if published_only else None
        if cursor is not None and cursor.published_at is not None:
            stmt = stmt.where(tuple_(AiArticle.published_at, AiArticle.article_id)
                              < tuple_(cursor.published_at, cursor.article_id))
        else:
            stmt = stmt.where(AiArticle.article_id < before_id)
    order = AiArticle.published_at.desc() if published_only else AiArticle.article_id.desc()
    return list(db.scalars(stmt.order_by(order, AiArticle.article_id.desc()).limit(min(limit, 100))))


def get_article(db: Session, club_id: int, article_id: int, *, admin: bool = False) -> AiArticle:
    a = _get(db, club_id, article_id)
    if not admin and not a.published_yn:
        raise NotFound("기사를 찾을 수 없습니다.", "ARTICLE_NOT_FOUND")
    return a


def list_insights(db: Session, club_id: int, session_id: int | None = None, include_inactive: bool = False) -> list[dict]:
    stmt = select(Insight).where(Insight.club_id == club_id)
    if session_id:
        stmt = stmt.where(Insight.session_id == session_id)
    if not include_inactive:
        stmt = stmt.where(Insight.active_yn.is_(True))
    rows = list(db.scalars(stmt.order_by(Insight.importance.desc(), Insight.insight_id).limit(500)))
    return [
        {"insightId": i.insight_id, "sessionId": i.session_id, "matchId": i.match_id, "memberId": i.member_id,
         "type": i.insight_type, "category": i.category, "phase": i.phase, "importance": i.importance,
         "facts": i.facts_json, "ruleVersion": i.rule_version, "active": i.active_yn, "createdAt": to_iso(i.created_at)}
        for i in rows
    ]
