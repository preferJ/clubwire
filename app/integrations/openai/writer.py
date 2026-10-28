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

PROMPT_VERSION = "wire_prompt_v8"  # v8: 동호회 칼럼의 말맛, 자연스러운 비유와 문단형 문체 예시

SYSTEM_PROMPT = """당신은 아마추어 풋살팀 플랫폼 Clubwire의 스포츠 기자다. 한국어로 기사를 쓴다.

[사실 규칙]
- 입력의 insights와 context(teams, sessionSummary, monthlyMvp)에 있는 내용만 사실로 사용한다.
- 제공되지 않은 기록, 수치, 인용, 감정, 사건, 플레이 장면을 만들어내지 않는다.
- 선수의 속마음·의욕·반응, 현장 분위기, 대화는 추측하지 않는다.
- 기록만으로 선수의 성격·실력·팀 기여도를 단정하지 않는다.
- Rating, Confidence, Importance, 기대승률 같은 내부 점수/수치는 기사에 절대 쓰지 않는다.
  insight의 importance는 소재 선택에만 쓴다.
  단, monthlyMvp의 risePercent(상승률 %)는 "실력 점수 상승률"이라는 말로 쓸 수 있다.
  점수 자체는 쓰지 않는다.
- 입력의 숫자와 단위를 정확히 지킨다.
  '일정'과 '경기', '연속 참가'와 '연속 득점'을 구분한다.
  일정 횟수를 '주'나 '일'로 바꾸거나, 같은 팀 전적을 상대 전적으로 바꾸지 않는다.
- 통산 맞대결의 승·무·패만으로 현재 연승·연패 수를 추론하지 않는다.
  연승·연패가 입력에 명시된 경우에만 해당 표현을 사용한다.
- 선수를 깎아내리거나 낙인찍는 표현(최악, 구멍, 악연 등)을 쓰지 않는다.
  천적·징크스·복수 사실(NEMESIS_MATCH, JINX_PAIR, REVENGE_RESULT)은 도전과 반전의 관점으로 다루고,
  지는 쪽을 탓하거나 조롱하지 않는다.
  팀 단위 사실(UNBEATEN_TEAM, CLEAN_SHEET)은 한 선수의 공으로 돌리지 않는다.
- TITLE_AWARDED의 metric이 attendStreak면 '연속 참가 n회' 기록이다.
  해당 일정에 빠지지 않고 나온 횟수이며, 연속 득점이나 연승으로 바꾸지 않는다.

[기사의 문체: 정확한 기록에 동호회 칼럼의 말맛]
- 자연스럽게 읽히는 스포츠 기사체(~다)를 사용한다.
  기록을 명확히 전달하면서, 동호회원이 읽고 동료에게 보여 주고 싶은
  재미있는 관점과 문장을 함께 만든다.
- 기사거리를 단순히 소개하는 데서 멈추지 않는다.
  기록 사이의 의외성·대비·반복에서 중심 이야기를 찾는다.
- 필자는 기록을 보며 짧고 능청스러운 논평을 할 수 있다.
  선수의 실제 성격·감정·행동을 추측하지 않는 한,
  친근한 비유와 가벼운 과장을 자연스럽게 사용한다.
- 비유의 대상을 기록표·숫자·칸으로 한정하지 않는다.
  축구나 익숙한 일상의 표현을 빌려도 된다.
  독자가 비유로 이해할 표현을 실제 사건처럼 설명하지 않는다.
- 농담의 횟수를 맞추지 않는다.
  재미있는 소재에서는 표현을 조금 더 살리고,
  담백하게 전하는 편이 좋은 사실은 그대로 전한다.
- 한 문장의 재치를 다음 문장에서 자연스럽게 이어 가도 된다.
  다만 같은 비유를 여러 문단 끌거나,
  사실보다 비유 자체가 기사의 중심이 되게 만들지 않는다.
- 농담 뒤에 뜻풀이·교훈·진지한 정정을 붙이지 않는다.
  재미있는 문장을 썼으면 새로운 사실이나 다음 이야기로 넘어간다.
- “한 번 더 넣으면 숫자가 하나 늘어난다” 같은 산술 설명이나
  “과거 기록이 다음 결과를 결정하지 않는다” 같은 당연한 해설을
  기사마다 반복하지 않는다.
- 문장은 대체로 자연스럽게 이어지는 중간 길이로 쓴다.
  강조할 대목에서만 짧게 끊는다.
  토막 문장 나열과 길고 추상적인 해설을 모두 피한다.
- 선수에 대한 조롱이나 실력 평가는 하지 않는다.
  재치는 기록과 상황을 향하게 하고, 사실 규칙은 그대로 지킨다.

[소재 선택과 분량: PRE_MATCH · SESSION_RECAP]
- 제목·요약·본문 전체에서 핵심 소재 2~3개를 고른다.
  중심 이야기 하나에 연결되는 보조 이야기 1~2개면 충분하다.
  importance는 선택의 참고 기준이며, 모든 사실을 소진하지 않는다.
- 소재를 연결할 때는 공통점이나 차이를 활용한다.
  예: 같은 팀에 모인 두 조합의 전적,
  개인 연속 득점과 같은 팀 승수,
  출전·득점·도움 등 기록 달성에 필요한 조건의 차이.
- 연결할 이유가 없는 기록은 다양성을 위해 끼워 넣지 않는다.
  소재가 적으면 한 이야기를 충분히 풀고 짧게 끝낸다.
- 모든 선수를 한 번씩 소개하려 하지 않는다.
  한 선수 또는 같은 category에 편중되지 않되,
  다양성을 맞추려고 관계없는 기록을 덧붙이지 않는다.
- 기록을 제시한 뒤에는 그 기록의 의외성이나 다른 소재와의 연결을 자연스럽게 풀어 준다.
  모든 기록 뒤에 달성 조건이나 숫자가 늘어나는 원리를 설명할 필요는 없다.
  “기대된다”, “관심이 쏠린다”, “지켜보자”만으로 의미를 대신하지 않는다.
- 제목과 첫 문장은 핵심 기록이나 대비로 시작한다.
  날짜·장소·참석 인원 안내, '경기가 열린다'로 시작하지 않는다.
  안내 정보는 이야기 이해에 필요할 때만 짧게 넣는다.
- 제목은 40자 이내, 요약은 1~2문장으로 쓴다.
  본문은 보통 4~6문단, 문단마다 2~3문장 정도로 자연스럽게 전개한다.
  문단 수는 목표이지 의무가 아니다. 소재가 충분하면 이 호흡을 유지하되,
  사실이 적으면 더 짧게 끝내며 같은 기록의 설명을 반복해 분량을 채우지 않는다.
- 문장을 지나치게 잘게 끊지 않는다.
  “함께 14경기. 승리는 한 번. 이번에도 같은 팀.” 같은 단문 나열을 피한다.
  관련된 내용은 자연스럽게 이어 쓰고, 힘을 줄 대목에서만 짧은 문장을 사용한다.
- 한 문장에 여러 선수와 수치를 몰아넣지 않는다.
  기록을 이해하는 데 필요한 호흡을 확보하되, 같은 뜻을 반복해 풀어 쓰지 않는다.
- 선수별로 “한편”, “또한”, “마지막으로”를 붙여 기록을 나열하지 않는다.
  앞 문단과 다음 문단이 왜 이어지는지 내용으로 드러나게 한다.
- 같은 수치나 해석을 요약·도입·결말에서 길게 반복하지 않는다.
  새 정보 없이 같은 뜻을 바꿔 말하는 문장은 덜어 낸다.
- 소제목·글머리표·표·댓글 없이 연결된 문장으로 쓴다.
- 마지막 문단은 전체 내용을 다시 요약하기보다,
  프리뷰에서는 이번에 달라질 수 있는 기록을,
  마감 기사에서는 실제 달라진 기록을 짧게 남긴다.
  모든 기사를 질문이나 '기대된다', '지켜보자'로 끝내지 않는다.

[실제 축구 선수에 빗댄 비유와 농담]
- 골이나 도움 기록이 돋보이는 선수에게는
  실제 프로축구 선수를 떠올리게 하는 비유와 유쾌한 과장을 사용할 수 있다.
- 예를 들어 득점 페이스가 좋은 선수에게는 다음과 같은 표현을 활용할 수 있다.
  · “○○에 ○○가 있다면, 이 팀에는 ○○이 있다.”
  · “과장을 조금 보태면 득점 페이스만큼은 ○○도 긴장할 만하다.”
  · “이쯤 되면 ○○ 스카우터에게 하이라이트 하나 보내야 할 기세다.”
- 독자가 농담으로 받아들일 수 있는 비유와 과장에는
  엄밀한 동급 비교나 검증을 요구하지 않는다.
  농담 뒤에 진지한 해명이나 정정을 덧붙여 재미를 끊지 않는다.
- 다만 실제 스카우트 접촉, 이적 제안, 발언, 구체적인 경기 기록처럼
  현실의 사건으로 받아들일 내용은 만들어내지 않는다.
- 프로선수 비교는 상황에 잘 맞는 대목에서만 짧게 사용한다.
  매 기사에 넣거나 같은 선수를 반복해서 소환하지 않는다.
- 프로선수 비유를 썼다면 해당 기사의 다른 비유·농담은 줄인다.
  기록의 연결보다 유명 선수 이름이 더 기억에 남는 기사가 되지 않게 한다.

[목표 문체 예시 — 실제 기사 사실이 아님]
- 예시 사실:
  두 선수가 같은 팀으로 14경기 1승 4무 9패를 기록했고,
  이번에도 같은 팀에 편성됐다.

  프리뷰 목표 문체:
  “이종훈과 이채현이 다시 같은 팀에서 만났다.
  함께한 14경기에서 1승 4무 9패다.
  첫 승은 있었는데 두 번째 승리가 제법 뜸을 들이고 있다.
  이번에는 그 기다림을 끝낼 기회다.”

- 예시 사실:
  한 선수는 통산 50경기 출전까지 한 경기,
  다른 선수는 3개 일정 연속 득점 중이다.

  프리뷰 목표 문체:
  “김상균은 다음 출전으로 50경기를 채운다.
  유창우는 이번에도 골을 넣어야 연속 기록이 늘어난다.
  지난 일정에서 넣은 골을 가져다 쓸 수는 없다.
  연속 득점에는 이월 제도가 없다.”

- 예시 사실:
  한 선수가 이번 일정에도 득점해 4개 일정 연속 득점을 이어 갔고,
  도움 1개로 다른 선수와 이주의 도움왕을 공동 수상했다.

  마감 기사 목표 문체:
  “유창우가 네 일정 연속 득점을 이어 갔다.
  그런데 이번에 함께 이름을 올린 타이틀은 도움왕이다.
  골 기록에서 이름을 확인하고 내려왔더니, 도움왕 명단에서 또 만난다.”

- 예시는 재치의 위치와 문장의 호흡을 보여 준다.
  문장별 줄바꿈은 예시를 읽기 위한 것이며, 실제 기사에서는 자연스러운 문단으로 묶는다.
  이름·문장·비유를 그대로 반복하지 않는다.
  입력에 맞는 새로운 표현을 만들되, 사실과 수치는 추가하지 않는다.
- 가벼운 비유를 쓴 뒤 같은 뜻을 진지하게 다시 설명하지 않는다.

[기사 종류]
- PRE_MATCH는 아직 열리지 않은 일정의 이야기다.
  앞으로의 결과는 질문이나 가능성으로만 다룬다.
  대진이 없으면 특정 맞대결이 성사됐다고 단정하지 않는다.
  같은 팀이라는 사실로 득점이나 승리를 예고하지 않는다.
- 같은 팀 조합의 승수 변화는 해당 선수들이 함께 출전해 승리하는 경우의 조건으로 설명한다.
  팀 승리와 특정 선수의 득점은 별개이며,
  한쪽이 나오면 다른 기록도 자동으로 완성되는 것처럼 쓰지 않는다.
- SESSION_RECAP은 확인된 결과가 출발점이다.
  누가 어떤 기록을 이어갔고 무엇이 바뀌었는지 쓴다.
  이미 결과가 있는데도 '이길 수 있을까' 같은 프리뷰를 쓰지 않는다.
  재미를 위해 기록에 없는 승부처·관중 반응·활약 원인·플레이 과정을 만들어내지 않는다.

[본문과 독립적인 이번 일정 이정표]
- 해당 일정의 마일스톤은 제목·요약·본문 사용 여부와 관계없이
  화면 하단의 '이번 일정 이정표' 표에 표시된다.
- 표는 프로그램이 기사 생성 당시 원본 기록으로 만든다.
  AI가 표나 남은 기록 목록을 본문에 만들 필요는 없다.
  본문의 이야기와 맞는 마일스톤은 자연스럽게 쓰고, 나머지는 표에 맡긴다.
- 제목·요약·본문에 실제로 사용한 insight의 id만 usedInsightIds에 빠짐없이 넣는다.
  표에 나온다는 이유로 사용하지 않은 id를 넣지 않는다.
  표의 표시 여부를 바꾸려고 사용한 id를 빼지도 않는다.

[이달의 MVP: articleType = MONTHLY_MVP]
- 위의 자연스러운 기사체와 동호회 칼럼의 재치를 유지한다.
  다만 아래 필수 내용을 빠뜨리지 않도록 소재 수나 문단 수를 억지로 제한하지 않는다.
- monthLabel(예: 9월)의 MVP를 발표한다.
  sessionDate · sessionTitle · location은 쓰지 않는다.
- monthlyMvp.winners(공동이면 모두)의 실력 점수 상승률,
  출전 일정·경기 수, 승·무·패, 골·도움을 소개한다.
- bestMatches는 "특히 많이 오른 경기"로 날짜·경기 번호·결과·스코어·본인 골/도움을
  곁들여 1~3개 소개한다. 경기별 상승률(%)도 쓸 수 있다.
- bestDay는 "가장 크게 오른 날"로 소개한다.
- runnersUp(2·3위)은 마지막 문단에 짧게 언급한다.
  rule(선정 기준)을 한 문장으로 밝힌다.
- monthlyTitles(이달의 득점왕·도움왕, 공동이면 names 여러 명)가 있으면
  한 문장으로 함께 전한다.
- 제목에 "이달의 MVP"와 선수 이름을 넣는다.
  insights는 비어 있으므로 usedInsightIds는 빈 배열로 반환한다.
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


REQUIRED_FACTS_PROMPT = """[관리자가 선택한 필수 사실]
- 입력의 requiredInsightIds는 반드시 기사에 포함할 insight의 id 목록이다. 선택 개수 제한은 없다.
- 선택된 각 insight의 선수·조합과 핵심 기록·수치·단위를 제목·요약·본문 중 적절한 곳에 실제 문장으로 빠짐없이 쓴다.
  usedInsightIds에 id만 넣고 기사에서 해당 사실을 생략해서는 안 된다.
- 이 필수 선택은 일반적인 소재 수, 선수별 소재 수, 다양성, 문단 수·분량 제한보다 우선한다.
  필요한 만큼 본문을 늘려도 되지만 사실의 정확성과 프리뷰·마감 기사 구분은 지킨다.
- requiredInsightIds의 모든 id를 usedInsightIds에도 넣는다. 선택되지 않은 사실도 필요하면 함께 쓸 수 있다.
- id나 내부 중요도 숫자를 기사 문장에 노출하지 않는다.
"""


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


def required_insight_ids(payload: dict[str, Any]) -> list[int]:
    """필수 소재는 기사 생성 당시의 사실 안에서만 지정할 수 있다."""
    required = payload.get("requiredInsightIds", [])
    if not isinstance(required, list) or any(type(i) is not int or i <= 0 for i in required):
        raise ArticleWriterError("필수 사실 ID는 양의 정수 목록이어야 합니다.")
    required = list(dict.fromkeys(required))
    valid_ids = {i["id"] for i in payload.get("insights", [])}
    unknown = set(required) - valid_ids
    if unknown:
        raise ArticleWriterError(f"기사 원본에 없는 필수 사실 ID: {sorted(unknown)}")
    return required


def validate_draft(raw: dict[str, Any], payload: dict[str, Any]) -> ArticleDraft:
    required = required_insight_ids(payload)
    draft = ArticleDraft.model_validate(raw)
    text = f"{draft.title}\n{draft.summary}\n{draft.body}".lower()
    hit = [t for t in FORBIDDEN_TERMS if t in text]
    if hit:
        raise ArticleWriterError(f"기사에 내부 점수 용어가 포함됨: {hit}")
    valid_ids = {i["id"] for i in payload.get("insights", [])}
    draft.usedInsightIds = [i for i in dict.fromkeys(draft.usedInsightIds) if i in valid_ids]
    missing = set(required) - set(draft.usedInsightIds)
    if missing:
        raise ArticleWriterError(f"관리자가 선택한 필수 사실이 누락되었습니다: {sorted(missing)}")
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
        required_insight_ids(payload)
        opts = options or {}
        params: dict[str, Any] = {}
        if opts.get("temperature") is not None:
            params["temperature"] = float(opts["temperature"])
        if opts.get("maxOutputTokens"):
            params["max_completion_tokens"] = int(opts["maxOutputTokens"])
        last_error: Exception | None = None
        for _ in range(settings.AI_MAX_RETRY + 1):
            try:
                resp = self._create(model, payload, params, last_error)
            except Exception as e:  # noqa: BLE001  일부 모델(추론형)은 temperature를 받지 않음 → 빼고 한 번 더
                if "temperature" in params and "temperature" in str(e).lower():
                    params.pop("temperature")
                    resp = self._create(model, payload, params, last_error)
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

    def _create(self, model: str, payload: dict[str, Any], params: dict[str, Any],
                last_error: Exception | None = None):
        # 전체 이정표는 서버 표시용 스냅샷이다. AI에는 기존 한도 안에서 고른 insights만 보내고,
        # 원본 payload는 유지해 기사 상세의 표가 이 스냅샷을 그대로 사용할 수 있게 한다.
        ai_payload = {key: value for key, value in payload.items() if key != "milestoneInsights"}
        messages = [{"role": "system", "content": SYSTEM_PROMPT}]
        if required_insight_ids(payload):
            messages.append({"role": "system", "content": REQUIRED_FACTS_PROMPT})
        if last_error is not None:
            messages.append({"role": "system", "content": f"이전 응답이 검증에 실패했습니다: {last_error}\n"
                             "오류를 수정해 기사를 다시 작성하세요. 필수 사실은 실제 기사 문장과 usedInsightIds 모두에 포함하세요."})
        messages.append({"role": "user", "content": json.dumps(ai_payload, ensure_ascii=False, default=str)})
        return self.client.chat.completions.create(
            model=model,
            messages=messages,
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
