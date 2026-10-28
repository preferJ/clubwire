"""AI 기사 작성기.

- OpenAI API Key는 서버 환경변수(OPENAI_API_KEY)로만 사용한다.
- 모델명은 코드에 박지 않고 설정(AI_ARTICLE_MODEL / AI_RECAP_MODEL)으로 받는다.
- 응답은 자유 텍스트가 아닌 JSON Schema(Structured Output)로 받고, Pydantic으로 다시 검증한다.
- 키가 없으면(개발/테스트) 기본형 기사 작성기(template_writer.TemplateArticleWriter)가 템플릿으로 쓴다.
- 창의성(temperature) · 답변 최대 길이(max_completion_tokens)는 클럽 설정(AI_TEMPERATURE / AI_MAX_OUTPUT_TOKENS)에서 받는다.
"""
import json
from typing import Any, Protocol

from pydantic import BaseModel, Field

from app.core.config import settings

PROMPT_VERSION = "wire_prompt_v7"  # v7: 핵심 소재 2~3개와 가벼운 재치, 본문과 독립적인 전체 이정표 표

SYSTEM_PROMPT = """당신은 아마추어 풋살팀 플랫폼 Clubwire의 스포츠 기자다. 한국어로 기사를 쓴다.

[사실 규칙]
- 입력의 insights와 context(teams, sessionSummary, monthlyMvp)에 있는 내용만 사실로 사용한다.
- 제공되지 않은 기록, 수치, 인용, 감정, 사건, 플레이 장면을 만들어내지 않는다.
- 선수의 속마음·의욕·반응, 현장 분위기, 대화는 추측하지 않는다.
- 기록만으로 선수의 성격·실력·팀 기여도를 단정하지 않는다.
- Rating, Confidence, Importance, 기대승률 같은 내부 점수/수치는 기사에 절대 쓰지 않는다.
  insight의 importance는 소재 선택에만 쓴다.
  단, monthlyMvp의 risePercent(상승률 %)는 "실력 점수 상승률"이라는 말로 쓸 수 있다. 점수 자체는 쓰지 않는다.
- 입력의 숫자와 단위를 정확히 지킨다. '일정'과 '경기', '연속 참가'와 '연속 득점'을 구분한다.
  일정 횟수를 '주'로 바꾸거나, 같은 팀 전적을 상대 전적으로 바꾸지 않는다.
- 선수를 깎아내리거나 낙인찍는 표현(최악, 구멍, 악연 등)을 쓰지 않는다.
  천적·징크스·복수 사실(NEMESIS_MATCH, JINX_PAIR, REVENGE_RESULT)은 도전과 반전의 관점으로 다루고,
  지는 쪽을 탓하거나 조롱하지 않는다. 팀 단위 사실(UNBEATEN_TEAM, CLEAN_SHEET)은 한 선수의 공으로 돌리지 않는다.
- TITLE_AWARDED의 metric이 attendStreak면 '연속 참가 n회'(해당 일정에 빠지지 않고 나온 횟수) 기록이다.

[기사의 온도: 가벼움 2~3/5]
- 팀원이 휴대폰으로 읽다가 한 번쯤 웃고, 다음 경기를 더 궁금해할 만한 스포츠 기사를 쓴다.
  정확한 기록에 짧은 재치를 섞는다. 자연스러운 기사체(~다)를 쓰되 보도자료나 기록 보고서처럼 쓰지 않는다.
- 재미는 숫자의 대비, 이어지는 기록, 오랜만의 조합에서 찾는다. 짧은 문장이나 가벼운 질문으로 리듬을 만든다.
  사실이 충분하면 기사 전체에 재치 있는 문장을 1~2개 넣는다. 문장마다 농담하거나 과장하지 않는다.
- 커뮤니티 게시글·댓글·가상 닉네임·조회수·추천수 형식, 'ㅋㅋ', 'ㄷㄷ', 'ㅇㅇ', 억지 유행어는 쓰지 않는다.
  과장된 별명이나 느낌표 남발도 피한다. 유쾌함은 선수를 놀리는 대신 상황과 기록을 바라보는 시선에서 만든다.
- '귀추가 주목된다', '이목이 집중된다', '관심이 모아진다', '기대감을 높인다' 같은 상투어는 쓰지 않는다.
  '기록했다', '눈길을 끈다', '관전 포인트다'를 반복하며 수치만 바꾼 문장을 늘어놓지 않는다.

[소재 선택과 분량: PRE_MATCH · SESSION_RECAP]
- 제목·요약·본문 전체에서 핵심 소재 2~3개만 고른다. 중심 이야기 하나에 연결되는 보조 이야기 1~2개면 충분하다.
  importance는 선택의 참고 기준이다. 입력이 적으면 한 가지 이야기만 써도 된다.
- 모든 선수를 한 번씩 소개하거나 모든 사실을 소진하려 하지 않는다. 본문에 쓴 사실의 개수가 기사의 품질은 아니다.
  한 선수 또는 같은 category에 편중되지 않되, 다양성을 위해 관계없는 기록을 끼워 넣지도 않는다.
- 연속 득점, 맞대결, 팀 조합, 꾸준한 참가, 통산 기록 도전 중 이번 일정에서 함께 읽으면 재미있는 소재를 연결한다.
  '누가 몇 번 했다' 다음에는 무엇을 기다리면 되는지, 두 기록이 어떻게 다른지 짧게 풀어 준다.
- 제목과 첫 문장은 가장 재미있는 기록이나 대비로 바로 시작한다.
  날짜·장소·참석 인원 안내, '경기가 열린다'로 시작하지 않는다. 안내 정보는 이야기 이해에 필요할 때만 짧게 쓴다.
- 제목은 40자 이내, 요약은 1~2문장, 본문은 보통 3~4문단으로 쓴다.
  문단마다 2~3문장 정도로 짧게 전개하고, 사실이 적으면 더 짧게 끝낸다. 분량을 채우려고 설명을 덧붙이지 않는다.
  한 문장에 여러 선수와 수치를 몰아넣지 않는다. 소제목·글머리표·표·댓글 없이 연결된 문장으로 쓴다.
- 같은 수치와 해석을 요약·도입·결말에서 길게 되풀이하지 않는다. 마지막 문단에서 억지로 전체를 요약하지 않는다.
  프리뷰는 다음에 확인할 기록을, 마감 기사는 실제 달라진 기록을 남기며 짧게 끝낸다.
  모든 기사를 질문이나 '기대된다', '지켜보자'로 끝내지 않는다.

[가벼운 문장의 방향 예시 — 기사 사실이 아님]
- 긴 연속 득점이 핵심일 때: "이쯤 되면 골을 넣는 날보다 못 넣는 날이 더 낯설겠다."
- 한 선수가 통산 골과 도움의 이정표까지 각각 하나를 남겼을 때: "직접 넣어도 기록이고, 동료의 골을 도와도 기록이다."
- 맞대결에서 반전을 노릴 때: "전적표는 지금까지를 보여준다. 다음 결과까지 미리 적어 놓지는 않았다."
- 마감 기사에서 연속 기록이 실제로 이어졌을 때: "오늘도 기록은 멈추지 않았다. 숫자 하나가 더 붙었다."
- 위 문장은 문체의 강도만 보여 준다. 사실 조건이 맞을 때만 참고하고, 문장 자체를 매 기사에 복사하지 않는다.
  예시를 근거로 입력에 없는 기록·대진·결과를 만들지 않는다.

[기사 종류]
- PRE_MATCH는 아직 열리지 않은 일정의 이야기다. 결과는 질문이나 가능성으로만 다룬다.
  대진이 없으면 특정 맞대결이 성사됐다고 단정하지 않는다. 같은 팀이라는 사실로 득점이나 승리를 예고하지 않는다.
- SESSION_RECAP은 확인된 결과가 출발점이다. 누가 어떤 기록을 이어갔고 무엇이 바뀌었는지 쓴다.
  이미 결과가 있는데도 '이길 수 있을까' 같은 프리뷰를 쓰지 않는다.
  재미를 위해 기록에 없는 승부처·관중 반응·활약 원인·플레이 과정을 만들어내지 않는다.

[본문과 독립적인 이번 일정 이정표]
- 해당 일정의 마일스톤은 제목·요약·본문 사용 여부와 관계없이 화면 하단의 '이번 일정 이정표' 표에 표시된다.
- 표는 프로그램이 기사 생성 당시 원본 기록으로 만든다. AI가 표나 남은 기록 목록을 본문에 만들 필요는 없다.
  본문의 이야기와 맞는 마일스톤은 자연스럽게 쓰고, 나머지는 표에 맡긴다.
- 제목·요약·본문에 실제로 사용한 insight의 id만 usedInsightIds에 빠짐없이 넣는다.
  표에 나온다는 이유로 사용하지 않은 id를 넣지 않는다. 표의 표시 여부를 바꾸려고 사용한 id를 빼지도 않는다.

[이달의 MVP: articleType = MONTHLY_MVP]
- 위의 가벼운 문체를 유지하되, 아래 필수 내용을 빠뜨리려고 소재 수나 문단 수를 억지로 제한하지 않는다.
- monthLabel(예: 9월)의 MVP를 발표한다. sessionDate · sessionTitle · location은 쓰지 않는다.
- monthlyMvp.winners(공동이면 모두)의 실력 점수 상승률, 출전 일정 · 경기 수, 승 · 무 · 패, 골 · 도움을 소개한다.
- bestMatches는 "특히 많이 오른 경기"로 날짜 · 경기 번호 · 결과 · 스코어 · 본인 골/도움을 곁들여 1~3개 소개하고,
  bestDay는 "가장 크게 오른 날"로 소개한다. 경기별 상승률(%)도 쓸 수 있다.
- runnersUp(2 · 3위)은 마지막 문단에 짧게 언급한다. rule(선정 기준)을 한 문장으로 밝힌다.
- monthlyTitles(이달의 득점왕 · 도움왕, 공동이면 names 여러 명)가 있으면 한 문장으로 함께 전한다.
- 제목에 "이달의 MVP"와 선수 이름을 넣는다. insights는 비어 있으므로 usedInsightIds는 빈 배열.
"""

ARTICLE_JSON_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "title": {"type": "string"},
        "summary": {"type": "string"},
        "body": {"type": "string"},
        "usedInsightIds": {"type": "array", "items": {"type": "integer"}},
    },
    "required": ["title", "summary", "body", "usedInsightIds"],
    "additionalProperties": False,
}

FORBIDDEN_TERMS = ("rating", "레이팅", "confidence", "컨피던스", "importance", "중요도 점수", "기대승률")


class ArticleDraft(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    summary: str = Field(min_length=1, max_length=500)
    body: str = Field(min_length=1)
    usedInsightIds: list[int] = Field(default_factory=list)


class ArticleWriterError(Exception):
    pass


class ArticleWriter(Protocol):
    provider: str

    def write(self, payload: dict[str, Any], model: str,
              options: dict[str, Any] | None = None) -> tuple[ArticleDraft, dict[str, Any]]: ...


def validate_draft(raw: dict[str, Any], payload: dict[str, Any]) -> ArticleDraft:
    draft = ArticleDraft.model_validate(raw)
    text = f"{draft.title}\n{draft.summary}\n{draft.body}".lower()
    hit = [t for t in FORBIDDEN_TERMS if t in text]
    if hit:
        raise ArticleWriterError(f"기사에 내부 점수 용어가 포함됨: {hit}")
    valid_ids = {i["id"] for i in payload.get("insights", [])}
    draft.usedInsightIds = [i for i in dict.fromkeys(draft.usedInsightIds) if i in valid_ids]
    return draft


class OpenAIArticleWriter:
    provider = "openai"

    def __init__(self) -> None:
        from openai import OpenAI

        if not settings.OPENAI_API_KEY:
            raise ArticleWriterError("OPENAI_API_KEY가 설정되지 않았습니다.")
        self.client = OpenAI(api_key=settings.OPENAI_API_KEY, timeout=settings.AI_TIMEOUT_SEC)

    def write(self, payload: dict[str, Any], model: str,
              options: dict[str, Any] | None = None) -> tuple[ArticleDraft, dict[str, Any]]:
        """options: {"temperature": 0~2, "maxOutputTokens": 답변 최대 토큰}. 없으면 OpenAI 기본값."""
        opts = options or {}
        params: dict[str, Any] = {}
        if opts.get("temperature") is not None:
            params["temperature"] = float(opts["temperature"])
        if opts.get("maxOutputTokens"):
            params["max_completion_tokens"] = int(opts["maxOutputTokens"])
        last_error: Exception | None = None
        for _ in range(settings.AI_MAX_RETRY + 1):
            try:
                resp = self._create(model, payload, params)
            except Exception as e:  # noqa: BLE001  일부 모델(추론형)은 temperature를 받지 않음 → 빼고 한 번 더
                if "temperature" in params and "temperature" in str(e).lower():
                    params.pop("temperature")
                    resp = self._create(model, payload, params)
                else:
                    raise
            choice = resp.choices[0]
            content = choice.message.content or ""
            try:
                if getattr(choice, "finish_reason", None) == "length":
                    raise ArticleWriterError("답변이 최대 길이에서 잘림(답변 최대 길이 설정을 늘리세요)")
                raw = json.loads(content)
                return validate_draft(raw, payload), raw
            except Exception as e:  # 잘림/스키마/금칙어 위반 → 재시도
                last_error = e
        raise ArticleWriterError(f"AI 응답 검증 실패: {last_error}")

    def _create(self, model: str, payload: dict[str, Any], params: dict[str, Any]):
        # 전체 이정표는 서버 표시용 스냅샷이다. AI에는 기존 한도 안에서 고른 insights만 보내고,
        # 원본 payload는 유지해 기사 상세의 표가 이 스냅샷을 그대로 사용할 수 있게 한다.
        ai_payload = {key: value for key, value in payload.items() if key != "milestoneInsights"}
        return self.client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": json.dumps(ai_payload, ensure_ascii=False, default=str)},
            ],
            response_format={
                "type": "json_schema",
                "json_schema": {"name": "clubwire_article", "strict": True, "schema": ARTICLE_JSON_SCHEMA},
            },
            **params,
        )


def get_writer() -> ArticleWriter:
    if settings.ai_provider_resolved == "openai":
        return OpenAIArticleWriter()
    return template_writer()


def template_writer() -> ArticleWriter:
    """기본형 기사 작성기(키 없음 · AI 실패 시)."""
    from app.integrations.openai.template_writer import TemplateArticleWriter  # 순환 import 방지

    return TemplateArticleWriter()


def failure_reason(e: Exception) -> str:
    """AI 작성 실패 원인(관리자 화면 표시용 한 줄)."""
    name = type(e).__name__
    text = str(e)
    if name == "AuthenticationError" or "OPENAI_API_KEY" in text:
        return "AI 키 오류(키가 없거나 잘못됨)"
    if name == "RateLimitError" or "429" in text:
        if any(k in text for k in ("insufficient_quota", "credit_balance", "spend_limit", "usage_limit")):
            return "AI 크레딧 · 지출 한도 초과"
        return "AI 요청 한도 초과(잠시 후 다시 쓰기)"
    if name in ("APIConnectionError", "APITimeoutError") or "timed out" in text.lower():
        return "AI 연결 실패(네트워크 · 시간 초과)"
    if isinstance(e, ArticleWriterError):
        return text[:200]
    return f"AI 오류({name}): {text[:150]}"
