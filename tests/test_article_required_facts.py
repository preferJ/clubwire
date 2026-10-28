"""관리자 필수 사실 선택: API → 재생성 스냅샷 → 실제 기사 내용."""
from copy import deepcopy

import pytest
from sqlalchemy import func, select

from app.core.database import SessionLocal
from app.models import AiArticle, Insight, Member
from app.models.enums import ArticleStatus, ArticleType
from app.services.common import get_club_by_slug


def _seed_article(api, count=3):
    """실제 FK를 가진 사실과, 그중 일부만 포함한 과거 기사 스냅샷."""
    with SessionLocal() as db:
        club = get_club_by_slug(db, api.slug)
        facts = []
        for n in range(count + 1):
            name = f"필수{n + 1:02d}선수"
            member = Member(club_id=club.club_id, name=name)
            db.add(member)
            db.flush()
            person = {"memberId": member.member_id, "name": name}
            insight = Insight(
                club_id=club.club_id, member_id=member.member_id,
                insight_type="FIRST_APPEARANCE", category="PLAYER", phase="PRE",
                importance=50 - n, rule_version="first_appearance_v1",
                facts_json={"member": person, "teamCode": "A", "firstAppearance": True},
            )
            db.add(insight)
            db.flush()
            facts.append({
                "id": insight.insight_id, "type": insight.insight_type,
                "category": insight.category, "importance": insight.importance,
                "subject": person, "facts": deepcopy(insight.facts_json),
            })
        payload = {
            "articleType": "PRE_MATCH", "clubName": club.club_name,
            "sessionDate": "2026-10-17", "sessionTitle": "원본 일정",
            "location": None, "insights": facts[:count],
            "teams": [{"teamCode": "A", "members": [f["subject"]["name"] for f in facts[:count]],
                       "guestCount": 0}],
        }
        article = AiArticle(
            club_id=club.club_id, article_type=ArticleType.PRE_MATCH,
            title="보존할 원본 제목", summary="보존할 원본 요약", content="보존할 원본 본문",
            model_name="stub", prompt_version="original_prompt", status=ArticleStatus.GENERATED,
            generation_no=1, request_json=payload,
        )
        db.add(article)
        db.commit()
        return article.article_id, deepcopy(payload), facts[-1]["id"]


def _version_count():
    with SessionLocal() as db:
        return db.scalar(select(func.count()).select_from(AiArticle))


def test_regenerate_includes_all_fifteen_required_facts_and_preserves_source(make_club):
    api = make_club("required-all")
    original_id, original_payload, _ = _seed_article(api, count=15)
    ids = [i["id"] for i in original_payload["insights"]]

    new = api.ok(api.post(f"/articles/{original_id}/regenerate", {"requiredInsightIds": ids}), 201)
    assert new["status"] == "GENERATED", new
    assert new["articleId"] != original_id
    assert new["generationNo"] == 2 and new["parentArticleId"] == original_id
    assert new["requestJson"]["requiredInsightIds"] == ids
    assert new["requestJson"]["insights"] == original_payload["insights"]
    assert set(new["usedInsightIds"]) == set(ids)
    for insight in original_payload["insights"]:
        assert insight["subject"]["name"] in new["content"]

    original = api.ok(api.get(f"/articles/{original_id}"))
    assert original["requestJson"] == original_payload
    assert original["title"] == "보존할 원본 제목"
    assert original["content"] == "보존할 원본 본문"
    assert original["status"] == "GENERATED" and original["generationNo"] == 1


def test_required_facts_deduplicate_inherit_and_can_be_cleared(make_club):
    api = make_club("required-options")
    original_id, payload, _ = _seed_article(api)
    first_id, last_id = payload["insights"][0]["id"], payload["insights"][-1]["id"]
    selected = [last_id, first_id]
    new = api.ok(api.post(f"/articles/{original_id}/regenerate",
                         {"requiredInsightIds": [last_id, first_id, last_id]}), 201)
    assert new["requestJson"]["requiredInsightIds"] == selected

    # 오래된 클라이언트는 body를 안 보냄. 선택 누락은 기존 선택을 지우지 않는다.
    for body in (None, {}, {"requiredInsightIds": None}):
        previous = new
        new = api.ok(api.post(f"/articles/{previous['articleId']}/regenerate", body), 201)
        assert new["requestJson"]["requiredInsightIds"] == selected
        assert set(selected) <= set(new["usedInsightIds"])
        assert new["parentArticleId"] == original_id
        assert new["generationNo"] == previous["generationNo"] + 1

    cleared = api.ok(api.post(f"/articles/{new['articleId']}/regenerate",
                             {"requiredInsightIds": []}), 201)
    assert cleared["requestJson"]["requiredInsightIds"] == []
    assert api.ok(api.get(f"/articles/{new['articleId']}"))["requestJson"]["requiredInsightIds"] == selected

    legacy = api.ok(api.post(f"/articles/{original_id}/regenerate"), 201)
    assert legacy["status"] == "GENERATED"
    assert not legacy["requestJson"].get("requiredInsightIds")


def test_rejects_required_facts_outside_article_snapshot_without_creating_version(make_club):
    api = make_club("required-invalid")
    original_id, payload, outside_id = _seed_article(api)
    before = _version_count()
    for invalid_id in (outside_id, outside_id + 1000000):
        response = api.post(f"/articles/{original_id}/regenerate",
                            {"requiredInsightIds": [payload["insights"][0]["id"], invalid_id]})
        assert response.status_code == 400
        assert response.json()["error"]["code"] == "INVALID_REQUIRED_INSIGHTS"
        assert _version_count() == before
    assert api.ok(api.get(f"/articles/{original_id}"))["requestJson"] == payload


@pytest.mark.parametrize("invalid_id", [0, -1, True, "1", 1.0])
def test_required_fact_ids_must_be_positive_strict_integers(make_club, invalid_id):
    # 요청 형식 오류는 기사 조회/새 버전 생성 전에 거절되어야 한다.
    api = make_club(f"required-type-{str(invalid_id).lower().replace('.', '-')}")
    before = _version_count()
    response = api.post("/articles/999999/regenerate", {"requiredInsightIds": [invalid_id]})
    assert response.status_code == 422
    assert _version_count() == before


def test_required_facts_keep_admin_club_and_pending_guards(make_club):
    api = make_club("required-owner")
    other = make_club("required-other")
    original_id, payload, _ = _seed_article(api)
    body = {"requiredInsightIds": [payload["insights"][0]["id"]]}
    before = _version_count()
    assert api.post(f"/articles/{original_id}/regenerate", body, admin=False).status_code == 401
    assert other.post(f"/articles/{original_id}/regenerate", body).status_code == 404
    with SessionLocal() as db:
        article = db.get(AiArticle, original_id)
        article.status = ArticleStatus.PENDING
        db.commit()
    response = api.post(f"/articles/{original_id}/regenerate", body)
    assert response.status_code == 409 and response.json()["error"]["code"] == "ARTICLE_PENDING"
    assert _version_count() == before


@pytest.mark.parametrize("fallback_succeeds", [False, True])
def test_missing_required_fact_is_included_by_fallback_or_fails(make_club, monkeypatch, fallback_succeeds):
    """AI 누락 시 기본형도 필수 사실을 포함해야 하며, 불가능하면 실패로 남긴다."""
    import json
    from types import SimpleNamespace

    from app.core.config import settings
    from app.integrations.openai.writer import OpenAIArticleWriter
    from app.wire import article_service

    api = make_club(f"required-failure-{fallback_succeeds}")
    original_id, payload, _ = _seed_article(api)
    api.ok(api.patch("/admin/config", {"values": {"ARTICLE_PUBLISH_MODE": "AUTO"}}))
    monkeypatch.setattr(settings, "AI_MAX_RETRY", 1)
    calls = []

    def create(**kwargs):
        calls.append(kwargs)
        content = json.dumps({"title": "누락된 결과", "summary": "요약", "body": "본문", "usedInsightIds": []})
        return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=content))])

    writer = OpenAIArticleWriter.__new__(OpenAIArticleWriter)
    writer.client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))
    monkeypatch.setattr(article_service, "get_writer", lambda: writer)
    if not fallback_succeeds:
        monkeypatch.setattr(article_service, "template_writer", lambda: writer)
    selected = payload["insights"][0]
    new = api.ok(api.post(f"/articles/{original_id}/regenerate",
                         {"requiredInsightIds": [selected["id"]]}), 201)
    if fallback_succeeds:
        assert len(calls) == 2
        assert new["status"] == "GENERATED" and new["basic"]
        assert selected["id"] in new["usedInsightIds"]
        assert selected["subject"]["name"] in new["content"]
    else:
        assert len(calls) == 4
        assert new["status"] == "FAILED" and new["publishedAt"] is None
        assert "필수 사실이 누락" in new["errorMessage"]
        assert new["usedInsightIds"] == []
    assert api.ok(api.get(f"/articles/{original_id}"))["content"] == "보존할 원본 본문"
