"""AI 기사 작성기.

- OpenAI API Key는 서버 환경변수(OPENAI_API_KEY)로만 사용한다.
- 모델명은 코드에 박지 않고 설정(AI_ARTICLE_MODEL / AI_RECAP_MODEL)으로 받는다.
- 응답은 자유 텍스트가 아닌 JSON Schema(Structured Output)로 받고, Pydantic으로 다시 검증한다.
- 키가 없으면(개발/테스트) StubArticleWriter가 템플릿으로 기사를 만든다.
"""
import json
from typing import Any, Protocol

from pydantic import BaseModel, Field

from app.core.config import settings

PROMPT_VERSION = "wire_prompt_v1"

SYSTEM_PROMPT = """당신은 아마추어 풋살팀 플랫폼 Clubwire의 스포츠 기자다. 한국어로 기사를 쓴다.

[사실 규칙]
- 입력의 insights와 context(teams, sessionSummary)에 있는 내용만 사실로 사용한다.
- 제공되지 않은 기록, 수치, 인용, 감정, 사건을 만들어내지 않는다.
- Rating, Confidence, Importance, 기대승률 같은 내부 점수/수치는 기사에 절대 쓰지 않는다.
  (insight의 importance는 뉴스 가치 판단에만 쓴다)
- 선수를 깎아내리거나 부정적으로 낙인찍는 표현(최악, 구멍, 악연 등)을 쓰지 않는다.

[구성 규칙]
- importance가 높을수록 뉴스 가치가 높다. 모든 insight를 쓸 필요는 없다.
- 한 선수에게 지나치게 편중되지 않게 하고, 같은 category를 반복해서 나열하지 않는다.
- 제목은 40자 이내, 요약은 1~2문장, 본문은 3~6개 문단.
- articleType이 PRE_MATCH면 오늘 일정의 관전 포인트(프리뷰), SESSION_RECAP이면 오늘 일정 결과 정리(마감 기사)로 쓴다.
- 사용한 insight의 id를 usedInsightIds에 반드시 모두 넣는다. 사용하지 않은 id는 넣지 않는다.
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

    def write(self, payload: dict[str, Any], model: str) -> tuple[ArticleDraft, dict[str, Any]]: ...


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

    def write(self, payload: dict[str, Any], model: str) -> tuple[ArticleDraft, dict[str, Any]]:
        last_error: Exception | None = None
        for _ in range(settings.AI_MAX_RETRY + 1):
            resp = self.client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": json.dumps(payload, ensure_ascii=False, default=str)},
                ],
                response_format={
                    "type": "json_schema",
                    "json_schema": {"name": "clubwire_article", "strict": True, "schema": ARTICLE_JSON_SCHEMA},
                },
            )
            content = resp.choices[0].message.content or ""
            try:
                raw = json.loads(content)
                return validate_draft(raw, payload), raw
            except Exception as e:  # 스키마/금칙어 위반 → 재시도
                last_error = e
        raise ArticleWriterError(f"AI 응답 검증 실패: {last_error}")


class StubArticleWriter:
    """OpenAI 키 없이 개발/테스트할 때 쓰는 템플릿 작성기(사실만 나열)."""

    provider = "stub"

    TEMPLATES = {
        "RETURN_PLAYER": "{name}이(가) {daysSinceLastAppearance}일 만에 돌아온다.",
        "RETURN_PLAYER_RESULT": "{daysSinceLastAppearance}일 만에 복귀한 {name}은(는) {gamesToday}경기에서 {goalsToday}골을 기록했다.",
        "FIRST_APPEARANCE": "{name}이(가) Clubwire 첫 경기에 나선다.",
        "WIN_STREAK": "{name}은(는) {streak}연승을 이어가고 있다.",
        "SCORING_STREAK": "{name}은(는) {streak}개 일정 연속 득점 중이다.",
        "MILESTONE_EXPECTED": "{name}은(는) {metricLabel} {milestone}개까지 {remaining}개를 남겨두고 있다.",
        "MILESTONE_ACHIEVED": "{name}이(가) 통산 {metricLabel} {milestone}개를 달성했다.",
        "RARE_PAIR": "{names}이(가) 오랜만에 같은 팀에서 호흡을 맞춘다.",
        "CLOSE_MATCH_EXPECTED": "오늘 팀 간 전력은 매우 균형적이다.",
        "LATE_WINNER": "{name}이(가) {gameNo}경기 종료 {remainingSec}초 전 결승골을 터뜨렸다.",
        "COMEBACK_WIN": "TEAM {winnerTeam}이(가) {gameNo}경기에서 {maxDeficit}골 차를 뒤집었다.",
        "UPSET_WIN": "{gameNo}경기에서 TEAM {winnerTeam}이(가) 예상을 깨고 승리했다.",
        "HAT_TRICK": "{name}이(가) {gameNo}경기에서 {goals}골을 몰아쳤다.",
        "TITLE_AWARDED": "{name}이(가) {titleName}에 올랐다.",
    }

    def write(self, payload: dict[str, Any], model: str) -> tuple[ArticleDraft, dict[str, Any]]:
        insights = sorted(payload.get("insights", []), key=lambda i: -i["importance"])
        used, lines, per_member = [], [], {}
        for ins in insights:
            facts = dict(ins["facts"])
            subject = (ins.get("subject") or {}).get("name") or ""
            if subject and per_member.get(subject, 0) >= 2:
                continue
            facts.setdefault("name", subject)
            facts["names"] = ", ".join(m.get("name") or "" for m in facts.get("members", []))
            tpl = self.TEMPLATES.get(ins["type"])
            if not tpl:
                continue
            try:
                lines.append(tpl.format(**facts))
            except (KeyError, IndexError):
                continue
            used.append(ins["id"])
            if subject:
                per_member[subject] = per_member.get(subject, 0) + 1
            if len(used) >= 6:
                break
        kind = "프리뷰" if payload.get("articleType") == "PRE_MATCH" else "마감"
        title = f"[{kind}] {lines[0]}" if lines else f"[{kind}] {payload.get('sessionDate')} {payload.get('clubName')}"
        summary_obj = payload.get("sessionSummary") or {}
        extra = []
        for m in summary_obj.get("matches", []):
            extra.append(f"{m['gameNo']}경기 TEAM {m['teamA']} {m['scoreA']} : {m['scoreB']} TEAM {m['teamB']}")
        body = "\n\n".join(lines + (["\n".join(extra)] if extra else [])) or "오늘의 경기 소식입니다."
        raw = {"title": title[:120], "summary": (lines[0] if lines else title)[:300], "body": body, "usedInsightIds": used}
        return validate_draft(raw, payload), raw


def get_writer() -> ArticleWriter:
    if settings.ai_provider_resolved == "openai":
        return OpenAIArticleWriter()
    return StubArticleWriter()
