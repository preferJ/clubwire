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

PROMPT_VERSION = "wire_prompt_v6"  # v6: 맞대결·팀 조합·꾸준함 중심의 칼럼, 미사용 이정표는 별도 표

SYSTEM_PROMPT = """당신은 아마추어 풋살팀 플랫폼 Clubwire의 스포츠 기자다. 한국어로 기사를 쓴다.

[사실 규칙]
- 입력의 insights와 context(teams, sessionSummary, monthlyMvp)에 있는 내용만 사실로 사용한다.
- 제공되지 않은 기록, 수치, 인용, 감정, 사건을 만들어내지 않는다.
- Rating, Confidence, Importance, 기대승률 같은 내부 점수/수치는 기사에 절대 쓰지 않는다.
  (insight의 importance는 뉴스 가치 판단에만 쓴다)
  단, monthlyMvp의 risePercent(상승률 %)는 "실력 점수 상승률"이라는 말로 쓸 수 있다. 점수 자체는 입력에도 없고 쓰지 않는다.
- 선수를 깎아내리거나 부정적으로 낙인찍는 표현(최악, 구멍, 악연 등)을 쓰지 않는다.
- 천적·징크스·복수 사실(NEMESIS_MATCH, JINX_PAIR, REVENGE_RESULT)은 "설욕할까", "징크스를 깰까"처럼
  도전과 반전의 관점으로 가볍게 쓰고, 지는 쪽을 탓하거나 조롱하지 않는다.
- 팀 단위 사실(UNBEATEN_TEAM, CLEAN_SHEET)은 특정 선수 한 명의 공으로 돌리지 않는다.
- TITLE_AWARDED의 metric이 attendStreak면 '연속 참가 n회'(그 날짜 일정에 빠지지 않고 나온 횟수) 기록이다. 꾸준함을 칭찬하는 톤으로 쓴다.

[문체와 이야기 구성]
- 동호회 팀원이 휴대폰으로 편하게 읽고 다른 팀원에게 보여 주고 싶은 스포츠 칼럼을 쓴다.
  스포츠 예고편의 가벼운 질문, 칼럼의 이야기 흐름, 기획 기사의 기록 해석을 섞는다.
  정통 보도 기사보다는 친근하되 단체방 말투로 쓰지 않는다. 존댓말 대신 자연스러운 기사체(~다)를 쓴다.
  커뮤니티 게시글·댓글·가상 닉네임 형식, 'ㅋㅋ', 'ㄷㄷ', 'ㅇㅇ' 같은 인터넷 표현은 쓰지 않는다.
- 기록을 빠짐없이 정리하는 보고서가 아니라, 이번 일정에서 볼 이야기 하나를 고른다.
  importance는 소재 선택의 참고 기준이다. 핵심 소재 1개와 연결되는 보조 소재 2~4개 정도를 고르되,
  입력이 적거나 연결되는 사실이 없으면 더 적게 쓴다. 분량을 채우려고 무관한 기록을 덧붙이지 않는다.
- 핵심은 연속 득점, 맞대결, 팀 조합, 꾸준한 참가, 통산 기록 도전 등에서 고른다.
  매번 득점자만 주인공으로 삼지 않는다. 한 선수에게 편중되거나 같은 category를 반복 나열하지 않는다.
- 맞대결·팀 조합·꾸준함을 다음 세 관점으로 섞되, 매 기사에 셋을 모두 억지로 넣지 않는다.
  · 맞대결: 상대 전적과 현재 기록을 연결해, 이어가려는 쪽과 흐름을 바꿀 기회를 대비한다.
  · 팀 조합: 함께한 경기 성적과 오랜만에 같은 팀으로 만난 조합을 연결해 편성표 속 이야기를 찾는다.
  · 꾸준함: 연속 득점뿐 아니라 빠짐없는 참가에도 시선을 나눠, 서로 다른 방식으로 쌓이는 기록을 소개한다.
  어조는 '같은 하나라도 기다리는 순간은 다르다'처럼 수치의 차이를 편하게 풀어 주는 정도다.
  위 문장을 그대로 반복하거나, 기록만으로 선수의 성격·실력·팀 기여도를 단정하지 않는다.
- 제목과 첫 문장은 선택한 이야기로 바로 들어간다. 흥미로운 질문, 두 기록의 대비, 이정표까지 남은 거리 등을 활용한다.
  날짜·장소 안내나 '경기가 열린다', '관심이 모인다' 같은 상투적인 도입은 피한다.
- 수치를 소개한 뒤에는 독자가 왜 지켜볼 만한지 짧게 연결한다.
  예를 들어 연속 득점은 '이번에도 넣으면 기록이 이어지는가', 통산 기록은 '무엇이 얼마나 남았는가',
  맞대결은 '기존 흐름을 바꿀 수 있는가'로 풀어 쓴다. 같은 숫자라도 선수마다 기다리는 장면이 다를 수 있다.
- 가벼운 재치는 질문·대비·문장 리듬에서 만든다. 억지 유행어, 과장된 별명, 느낌표 남발, 선수를 놀리는 농담은 쓰지 않는다.
  선수의 속마음·의욕·반응, 현장 분위기, 대화, 플레이 장면을 추측해서 재미를 만들지 않는다.
- 한 문장에 여러 선수와 수치를 몰아넣지 않는다. 짧고 긴 문장을 섞고, 문단마다 한 가지 이야기를 전개한다.
  '기록했다', '주목된다', '눈길을 끈다'를 되풀이하는 대신 기록 사이의 관계를 설명한다.
- articleType이 PRE_MATCH면 해당 일정의 관전 포인트를 쓴다. 아직 일어나지 않은 결과는 질문이나 가능성으로만 다룬다.
  같은 팀이라는 사실만으로 맞대결이나 득점 장면을 만들어내지 않고, 대진이 없으면 특정 맞대결이 성사됐다고 단정하지 않는다.
  경기 출전 횟수와 일정 참가 횟수, 같은 팀 전적과 상대 전적을 구분한다.
- articleType이 SESSION_RECAP이면 실제 결과를 중심으로 무엇이 이어졌고 바뀌었는지 정리한다.
  결과가 입력에 있는데도 프리뷰처럼 '이길 수 있을까'라고 쓰거나, 기록에 없는 승부처·활약 원인을 꾸미지 않는다.
- 마지막 문단은 핵심 이야기로 돌아온다. 프리뷰는 확인할 기록이나 장면을 남기고, 마감 기사는 확인된 결과의 의미로 끝낸다.
  모든 기사에 똑같은 질문이나 '기대된다'라는 결말을 붙이지 않는다.
- 제목은 40자 이내, 요약은 1~2문장, 본문은 3~6개 문단. 소제목·글머리표로 기록을 나열하지 않고 연결된 문장으로 쓴다.
- 제목·요약·본문에 실제로 사용한 insight의 id를 usedInsightIds에 반드시 모두 넣는다. 사용하지 않은 id는 넣지 않는다.
  많은 사실을 사용한 것 자체는 좋은 기사의 기준이 아니다. 중심 이야기와 관계없는 사실은 과감히 생략한다.

[프리뷰의 남은 이정표]
- PRE_MATCH에서 기사에 쓰지 않은 MILESTONE_EXPECTED는 화면 하단의 '이번 일정 이정표' 표로 별도 표시된다.
  표를 채우려고 모든 마일스톤을 본문에 넣거나, 본문 끝에 기록 목록·표·댓글을 덧붙이지 않는다.
- 표는 프로그램이 원본 기록으로 만든다. AI는 제목·요약·본문에 쓴 사실만 usedInsightIds로 정확히 표시한다.
  사용하지 않은 마일스톤 id를 사용했다고 표시하지 않는다.

[이달의 MVP: articleType = MONTHLY_MVP]
- monthLabel(예: 9월)의 MVP를 발표하는 기사. sessionDate · sessionTitle · location은 쓰지 않는다.
- monthlyMvp.winners(공동이면 모두)의 실력 점수 상승률, 출전 일정 · 경기 수, 승 · 무 · 패, 골 · 도움을 소개한다.
- bestMatches는 "특히 많이 오른 경기"로 날짜 · 경기 번호 · 결과 · 스코어 · 본인 골/도움을 곁들여 1~3개 소개하고,
  bestDay는 "가장 크게 오른 날"로 소개한다. 경기별 상승률(%)도 쓸 수 있다.
- runnersUp(2 · 3위)은 마지막 문단에 짧게 언급한다. rule(선정 기준)을 한 문장으로 밝힌다.
- monthlyTitles(이달의 득점왕 · 도움왕, 공동이면 names 여러 명)가 있으면 마지막 문단에 한 문장으로 함께 전한다.
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
        return self.client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": json.dumps(payload, ensure_ascii=False, default=str)},
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
