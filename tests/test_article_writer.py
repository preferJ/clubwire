"""AI 기사 설정(창의성 · 답변 최대 길이)과 기본형 기사 대체(키 없음 · 연결/한도/검증 실패)."""
import json
from types import SimpleNamespace

import httpx
import openai
import pytest

from app.core.config import settings

REQ = httpx.Request("POST", "https://api.openai.com/v1/chat/completions")
GOOD = {"title": "AI가 쓴 프리뷰", "summary": "요약", "body": "본문 문단", "usedInsightIds": []}


class FakeOpenAI:
    """openai.OpenAI 대역. behaviour(kwargs, n) → 응답 dict(또는 예외 발생). 호출 인자를 calls에 남긴다."""
    calls: list[dict] = []
    behaviour = None

    def __init__(self, **_):
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self._create))

    def _create(self, **kw):
        FakeOpenAI.calls.append(kw)
        out = FakeOpenAI.behaviour(kw, len(FakeOpenAI.calls))
        finish = out.pop("_finish", "stop")
        msg = SimpleNamespace(content=json.dumps(out, ensure_ascii=False))
        return SimpleNamespace(choices=[SimpleNamespace(message=msg, finish_reason=finish)])


@pytest.fixture
def ai(monkeypatch):
    """AI 사용 상태로 바꾸고 OpenAI 클라이언트를 대역으로."""
    monkeypatch.setattr(settings, "AI_PROVIDER", "openai")
    monkeypatch.setattr(settings, "OPENAI_API_KEY", "sk-test")
    monkeypatch.setattr(openai, "OpenAI", FakeOpenAI)
    FakeOpenAI.calls = []
    FakeOpenAI.behaviour = lambda kw, n: dict(GOOD)
    return FakeOpenAI


def _preview(api, slug_members=6):
    """일정 → 참석 → 팀 확정(= 프리뷰 기사 생성, 테스트는 동기 생성). 관리자 목록에서 그 기사 반환."""
    ids = [api.ok(api.post("/members", {"name": f"P{i}"}), 201)["memberId"] for i in range(slug_members)]
    sid = api.ok(api.post("/sessions", {"sessionDate": "2026-12-05"}), 201)["sessionId"]
    api.ok(api.post(f"/sessions/{sid}/members", {"memberIds": ids}))
    gen = api.ok(api.post(f"/sessions/{sid}/teams/generate", {"teamCount": 2}))
    api.ok(api.post(f"/sessions/{sid}/teams/confirm", {"generationId": gen["generationId"]}))
    arts = api.ok(api.get("/articles", params={"all": "true", "sessionId": sid}))
    return api.ok(api.get(f"/articles/{arts[0]['articleId']}"))


def test_creativity_and_length_settings_are_sent(make_club, ai):
    api = make_club("aiopt")
    api.ok(api.patch("/admin/config", {"values": {"AI_TEMPERATURE": 0.3, "AI_MAX_OUTPUT_TOKENS": 900}}))
    a = _preview(api)
    kw = ai.calls[-1]
    assert kw["temperature"] == 0.3 and kw["max_completion_tokens"] == 900
    assert a["title"] == "AI가 쓴 프리뷰" and a["basic"] is False and a["errorMessage"] is None
    assert a["modelName"] == settings.AI_ARTICLE_MODEL
    # 범위 밖 값은 저장 안 됨
    assert api.patch("/admin/config", {"values": {"AI_TEMPERATURE": 3}}).status_code == 400
    assert api.patch("/admin/config", {"values": {"AI_MAX_OUTPUT_TOKENS": 100}}).status_code == 400


def test_temperature_unsupported_model_retries_without_it(make_club, ai):
    def behaviour(kw, n):
        if "temperature" in kw:
            raise openai.BadRequestError("Unsupported parameter: 'temperature' is not supported with this model.",
                                         response=httpx.Response(400, request=REQ), body=None)
        return dict(GOOD)
    ai.behaviour = behaviour
    a = _preview(make_club("aitemp"))
    assert len(ai.calls) == 2 and "temperature" not in ai.calls[1] and "max_completion_tokens" in ai.calls[1]
    assert a["basic"] is False


@pytest.mark.parametrize("slug,error,reason", [
    ("aiconn", lambda: openai.APIConnectionError(request=REQ), "AI 연결 실패"),
    ("aiquota", lambda: openai.RateLimitError("Error code: 429 - insufficient_quota",
                                              response=httpx.Response(429, request=REQ), body=None), "크레딧 · 지출 한도"),
    ("aikey", lambda: openai.AuthenticationError("Incorrect API key", response=httpx.Response(401, request=REQ), body=None),
     "AI 키 오류"),
])
def test_ai_failure_falls_back_to_basic_article(make_club, ai, slug, error, reason):
    def behaviour(kw, n):
        raise error()
    ai.behaviour = behaviour
    api = make_club(slug)
    a = _preview(api)
    # 기본형으로 작성(검토 대기 = 평소 게시 규칙 MANUAL), 원인은 관리자에게
    assert a["status"] == "GENERATED" and a["basic"] is True and a["modelName"] == "template"
    assert a["errorMessage"].startswith("기본형으로 작성: ") and reason in a["errorMessage"]
    assert a["title"] and a["content"]

    # 게시 방식이 '바로 게시'면 기본형도 바로 게시. [다시 쓰기]에서 AI가 돌아오면 AI 기사
    api.ok(api.patch("/admin/config", {"values": {"ARTICLE_PUBLISH_MODE": "AUTO"}}))
    ai.behaviour = lambda kw, n: dict(GOOD)
    b = api.ok(api.post(f"/articles/{a['articleId']}/regenerate"), 201)
    b = api.ok(api.get(f"/articles/{b['articleId']}"))
    assert b["status"] == "PUBLISHED" and b["basic"] is False and b["title"] == "AI가 쓴 프리뷰"


def test_truncated_answer_retries_then_basic(make_club, ai):
    ai.behaviour = lambda kw, n: {**GOOD, "_finish": "length"}
    a = _preview(make_club("aitrunc"))
    assert len(ai.calls) == settings.AI_MAX_RETRY + 1
    assert a["basic"] is True and "잘림" in a["errorMessage"]


def test_no_key_writes_basic_article(make_club):
    """키 없음(테스트 기본 = 기본형 작성기): 처음부터 기본형, 원인 표시. 공개 화면에도 basic 표시."""
    api = make_club("nokey")
    a = _preview(api)
    assert a["basic"] is True and a["modelName"] == "template"
    assert a["errorMessage"] in ("기본형으로 작성: AI 키 없음(OPENAI_API_KEY)", "기본형으로 작성: AI 사용 안 함(AI_PROVIDER)")
    api.ok(api.post(f"/articles/{a['articleId']}/publish"))
    pub = api.ok(api.get(f"/articles/{a['articleId']}", admin=False))
    assert pub["basic"] is True and "errorMessage" not in pub and "modelName" not in pub
