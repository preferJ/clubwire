"""AI 기사: 생성 요청 → (백그라운드) OpenAI 호출 → 검증 → 저장/태그 → 게시.

AI로 못 쓰면(키 없음 · 크레딧/한도 초과 · 연결 오류 · 검증 실패) 기본형 기사(템플릿)로 대신 쓰고 평소 게시 규칙을 따른다.
기본형은 MODEL_NAME = 'template', 실패 원인은 ERROR_MESSAGE에 남겨 관리자 화면에 보여 준다([다시 쓰기]로 AI 재시도).
"""
import logging
from typing import Any

from sqlalchemy import delete, func, select, tuple_
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.database import SessionLocal, emit
from app.core.errors import BadRequest, Conflict, NotFound
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
from app.integrations.openai.writer import PROMPT_VERSION, failure_reason, get_writer, template_writer
from app.services.config_service import load_config
from app.services.session_service import team_rosters
from app.services.common import get_session

log = logging.getLogger("clubwire.wire")

ARTICLE_TYPE_TAG = {ArticleType.PRE_MATCH: "프리뷰", ArticleType.SESSION_RECAP: "마감", ArticleType.POST_MATCH: "경기",
                    ArticleType.MONTHLY_MVP: "이달의 MVP"}
# 게시 설정(ARTICLE_PUBLISH_MODE)과 상관없이 생성 즉시 게시하는 기사
ALWAYS_PUBLISH = {ArticleType.MONTHLY_MVP}
# 기본형(템플릿) 기사의 MODEL_NAME. sample-template = 샘플 데이터 생성기, stub = 예전 이름
TEMPLATE_MODEL = "template"
TEMPLATE_MODELS = {TEMPLATE_MODEL, "sample-template", "stub"}


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
        model_name=_model_for(article_type) if provider == "openai" else TEMPLATE_MODEL,
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
        session = db.get(ClubSession, a.session_id) if a.session_id else None
        if session and session.deleted_at is not None:
            return
        cfg = load_config(db, a.club_id)
        options = {"temperature": cfg["AI_TEMPERATURE"], "maxOutputTokens": cfg["AI_MAX_OUTPUT_TOKENS"]}
        reason = None
        try:
            writer = get_writer()
            draft, raw = writer.write(a.request_json or {}, a.model_name, options)
            if writer.provider != "openai":  # 처음부터 AI를 안 쓰는 설정
                reason = "AI 키 없음(OPENAI_API_KEY)" if not settings.OPENAI_API_KEY else "AI 사용 안 함(AI_PROVIDER)"
                a.model_name = TEMPLATE_MODEL
        except Exception as e:  # noqa: BLE001  AI 실패 → 기본형 기사로 대신
            log.warning("AI article failed, fallback to template: %s (%s)", article_id, e)
            reason = failure_reason(e)
            try:
                draft, raw = template_writer().write(a.request_json or {}, TEMPLATE_MODEL)
            except Exception as e2:  # noqa: BLE001  기본형까지 실패하면 실패로 남김
                log.exception("template article failed: %s", article_id)
                a.status = ArticleStatus.FAILED
                a.error_message = f"{reason} / 기본형 작성 실패: {e2}"[:4000]
                emit(db, a.club_id, "ARTICLE_UPDATED", {"articleId": a.article_id, "status": a.status})
                db.commit()
                return
            a.model_name = TEMPLATE_MODEL
        a.title, a.summary, a.content = draft.title, draft.summary, draft.body
        a.response_json = raw
        a.status = ArticleStatus.GENERATED
        a.error_message = f"기본형으로 작성: {reason}" if reason else None
        for iid in draft.usedInsightIds:
            db.add(AiArticleInsight(article_id=a.article_id, insight_id=iid))
        db.flush()
        _apply_tags(db, a)
        if a.article_type in ALWAYS_PUBLISH or (a.article_type != ArticleType.PRE_MATCH and cfg["ARTICLE_PUBLISH_MODE"] == "AUTO"):
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


def update_article(db: Session, club_id: int, article_id: int, *, title: str, summary: str, content: str,
                   used_insight_ids: list[int] | None = None) -> AiArticle:
    a = _get(db, club_id, article_id, lock=True)
    if a.session_id:
        get_session(db, club_id, a.session_id)
    if a.published_at is not None or a.status not in (ArticleStatus.GENERATED, ArticleStatus.REJECTED):
        raise Conflict("게시 전 기사만 수정할 수 있습니다.", "INVALID_ARTICLE_STATUS")
    if used_insight_ids is not None:
        selected = list(dict.fromkeys(used_insight_ids))
        payload = a.request_json if isinstance(a.request_json, dict) else {}
        insights = payload.get("insights")
        available = ({i["id"] for i in insights if isinstance(i, dict) and type(i.get("id")) is int}
                     if isinstance(insights, list) else set())
        valid = (set(db.scalars(select(Insight.insight_id).where(
            Insight.insight_id.in_(selected), Insight.club_id == club_id, Insight.session_id == a.session_id)))
                 if selected else set())
        if not set(selected) <= available or set(selected) != valid:
            raise BadRequest("이 기사에 전달된 사실만 선택할 수 있습니다.", "INVALID_ARTICLE_INSIGHTS")
        # 텍스트와 사용 사실을 한 트랜잭션에서 저장한다. 검증 실패 시 기존 내용은 그대로 둔다.
        db.execute(delete(AiArticleInsight).where(AiArticleInsight.article_id == article_id))
        db.add_all([AiArticleInsight(article_id=article_id, insight_id=i) for i in selected])
    a.title, a.summary, a.content = title, summary, content
    emit(db, club_id, "ARTICLE_UPDATED", {"articleId": a.article_id, "status": a.status})
    db.commit()
    return a


def publish_article(db: Session, club_id: int, article_id: int) -> AiArticle:
    a = _get(db, club_id, article_id, lock=True)
    if a.session_id:
        get_session(db, club_id, a.session_id)
    if a.status not in (ArticleStatus.GENERATED, ArticleStatus.REJECTED, ArticleStatus.SUPERSEDED):
        raise Conflict(f"게시할 수 없는 상태입니다({a.status}).", "INVALID_ARTICLE_STATUS")
    _publish(db, a)
    emit(db, club_id, "ARTICLE_UPDATED", {"articleId": a.article_id, "status": a.status})
    db.commit()
    return a


def reject_article(db: Session, club_id: int, article_id: int) -> AiArticle:
    a = _get(db, club_id, article_id, lock=True)
    if a.session_id:
        get_session(db, club_id, a.session_id)
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
    if src.session_id:
        get_session(db, club_id, src.session_id)
    if src.status == ArticleStatus.PENDING:
        raise Conflict("생성 중인 기사입니다.", "ARTICLE_PENDING")
    root_id = src.parent_article_id or src.article_id
    max_no = db.scalar(select(func.max(AiArticle.generation_no)).where(
        (AiArticle.article_id == root_id) | (AiArticle.parent_article_id == root_id))) or 1
    provider = settings.ai_provider_resolved
    a = AiArticle(
        club_id=club_id, session_id=src.session_id, match_id=src.match_id, article_type=src.article_type,
        model_name=_model_for(src.article_type) if provider == "openai" else TEMPLATE_MODEL,
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
def _unused_milestones(a: AiArticle, used: list[int]) -> list[dict]:
    """기사 작성 당시 사실 중 본문에 사용하지 않은 이정표만 공개한다.

    현재 선수 기록이나 최신 Insight를 조회하지 않아 과거 기사의 남은 수가 바뀌지 않는다.
    오래된 요청 데이터에 불완전한 항목이 있어도 기사 조회 자체는 계속 가능해야 한다.
    """
    if a.article_type != ArticleType.PRE_MATCH or not isinstance(a.request_json, dict):
        return []
    insights = a.request_json.get("insights")
    if not isinstance(insights, list):
        return []
    records = {"games": "경기 출전", "goals": "골", "assists": "도움"}
    seen = set(used)
    rows = []
    for insight in insights:
        if not isinstance(insight, dict) or insight.get("type") != "MILESTONE_EXPECTED":
            continue
        insight_id = insight.get("id")
        facts = insight.get("facts")
        if type(insight_id) is not int or insight_id <= 0 or insight_id in seen or not isinstance(facts, dict):
            continue
        person = facts.get("member") or insight.get("subject")
        if not isinstance(person, dict):
            continue
        member_id, name = person.get("memberId"), person.get("name")
        metric, milestone, remaining = facts.get("metric"), facts.get("milestone"), facts.get("remaining")
        if (type(member_id) is not int or member_id <= 0 or not isinstance(name, str) or not name.strip()
                or not isinstance(metric, str) or metric not in records
                or type(milestone) is not int or milestone <= 0
                or type(remaining) is not int or not 0 < remaining <= milestone):
            continue
        current = facts.get("current")
        if current is not None and (type(current) is not int or current < 0 or milestone - current != remaining):
            continue
        rows.append({"insightId": insight_id, "memberId": member_id, "name": name,
                     "record": f"통산 {milestone}{records[metric]}", "remaining": remaining})
        seen.add(insight_id)
    return rows


def serialize_article(db: Session, a: AiArticle, *, detail: bool = False, admin: bool = False) -> dict:
    tags = list(db.scalars(select(ArticleTag.tag_name).where(ArticleTag.article_id == a.article_id).order_by(ArticleTag.tag_name)))
    session = db.get(ClubSession, a.session_id) if a.session_id else None  # 화면에서 일정 날짜별로 묶기용
    data = {
        "articleId": a.article_id, "articleType": a.article_type, "sessionId": a.session_id,
        "sessionDate": session.session_date.isoformat() if session else None,
        "title": a.title, "summary": a.summary, "tags": tags, "status": a.status,
        "publishedAt": to_iso(a.published_at), "createdAt": to_iso(a.created_at),
        "generationNo": a.generation_no, "parentArticleId": a.parent_article_id,
        "basic": a.model_name in TEMPLATE_MODELS,  # 기본형(템플릿) 기사 여부. 화면 안내 문구용
    }
    if detail:
        data["content"] = a.content
        used = list(db.scalars(select(AiArticleInsight.insight_id).where(AiArticleInsight.article_id == a.article_id)))
        data["usedInsightIds"] = used
        data["unusedMilestones"] = _unused_milestones(a, used)
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
    stmt = stmt.where((AiArticle.session_id.is_(None)) | AiArticle.session_id.in_(
        select(ClubSession.session_id).where(ClubSession.deleted_at.is_(None))))
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
    session = db.get(ClubSession, a.session_id) if a.session_id else None
    if not admin and (not a.published_yn or (session and session.deleted_at is not None)):
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
