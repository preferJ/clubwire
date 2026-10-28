"""관리자가 선택한 필수 사실: 작성 지침, 누락 재시도, stub의 무제한 선택."""
import json
from types import SimpleNamespace

import pytest

from app.core.config import settings
from app.integrations.openai.writer import (
    ArticleWriterError,
    OpenAIArticleWriter,
    REQUIRED_FACTS_PROMPT,
    validate_draft,
)
from app.integrations.openai.template_writer import TemplateArticleWriter


def write_template(payload, model):
    return TemplateArticleWriter().write({"sessionDate": "2026-10-17", "articleType": "PRE_MATCH",
                                          "clubName": "테스트 FC", "teams": [], **payload}, model)


def insight(i, *, kind="WIN_STREAK", importance=50, name=None, facts=None):
    return {"id": i, "type": kind, "importance": importance,
            "subject": {"name": name or f"선수{i}", "memberId": i},
            "facts": {"streak": 3} if facts is None else facts}


def draft(used):
    return {"title": "기록 도전", "summary": "연속 기록에 도전한다.",
            "body": "선수1이 3연승을 이어가고 있다.", "usedInsightIds": used}


def fake_writer(replies):
    calls = []

    def create(**kw):
        calls.append(kw)
        raw = replies[min(len(calls) - 1, len(replies) - 1)]
        return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=json.dumps(raw)))])

    writer = OpenAIArticleWriter.__new__(OpenAIArticleWriter)
    writer.client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))
    return writer, calls


def test_validate_requires_every_selected_id_without_silently_adding_it():
    payload = {"insights": [insight(1), insight(2)], "requiredInsightIds": [1, 2]}
    raw = draft([1])
    with pytest.raises(ArticleWriterError, match="누락.*2"):
        validate_draft(raw, payload)
    assert raw["usedInsightIds"] == [1]
    assert validate_draft(draft([1, 2, 2, 999]), payload).usedInsightIds == [1, 2]


@pytest.mark.parametrize("required", [[999], [True], ["1"], [-1], "1", None])
def test_invalid_required_selection_is_not_ignored(required):
    with pytest.raises(ArticleWriterError):
        validate_draft(draft([1]), {"insights": [insight(1)], "requiredInsightIds": required})


def test_openai_retries_missing_required_fact_and_explains_it(monkeypatch):
    monkeypatch.setattr(settings, "AI_MAX_RETRY", 1)
    payload = {"insights": [insight(1)], "requiredInsightIds": [1]}
    writer, calls = fake_writer([draft([]), draft([1])])
    result, _ = writer.write(payload, "configured-model")
    assert result.usedInsightIds == [1] and len(calls) == 2
    assert calls[0]["model"] == "configured-model"
    assert calls[0]["response_format"]["json_schema"]["strict"] is True
    assert any(m["content"] == REQUIRED_FACTS_PROMPT for m in calls[0]["messages"])
    assert json.loads(calls[0]["messages"][-1]["content"]) == payload
    assert any("필수 사실이 누락" in m["content"] for m in calls[1]["messages"] if m["role"] == "system")


def test_openai_keeps_failure_after_retry_exhaustion(monkeypatch):
    monkeypatch.setattr(settings, "AI_MAX_RETRY", 1)
    writer, calls = fake_writer([draft([])])
    with pytest.raises(ArticleWriterError, match="AI 응답 검증 실패.*누락"):
        writer.write({"insights": [insight(1)], "requiredInsightIds": [1]}, "configured-model")
    assert len(calls) == 2


def test_required_openai_keeps_model_options_and_display_only_milestone_filter():
    payload = {"insights": [insight(1)], "requiredInsightIds": [1],
               "milestoneInsights": [{"id": 2, "type": "MILESTONE_EXPECTED"}]}
    writer, calls = fake_writer([draft([1])])
    writer.write(payload, "configured-model", {"temperature": 0.3, "maxOutputTokens": 900})
    assert calls[0]["temperature"] == 0.3 and calls[0]["max_completion_tokens"] == 900
    sent = json.loads(calls[0]["messages"][-1]["content"])
    assert sent == {key: value for key, value in payload.items() if key != "milestoneInsights"}
    assert "milestoneInsights" in payload


def test_stub_includes_fifteen_selected_facts_and_three_for_one_player():
    rows = [insight(1, name="공통선수"), insight(2, kind="SCORING_STREAK", name="공통선수"),
            insight(3, kind="FIRST_APPEARANCE", name="공통선수")]
    rows += [insight(i, kind="FIRST_APPEARANCE") for i in range(4, 16)]
    result, _ = write_template({"articleType": "PRE_MATCH", "insights": rows,
                                         "requiredInsightIds": list(range(1, 16))}, "stub")
    assert set(result.usedInsightIds) == set(range(1, 16))
    assert result.body.count("공통선수") == 3
    for i in range(4, 16):
        assert f"선수{i}" in result.body


def test_selected_low_importance_fact_is_not_starved_by_optional_facts():
    rows = [insight(i, importance=90) for i in range(1, 8)] + [insight(8, importance=1)]
    result, _ = write_template({"insights": rows, "requiredInsightIds": [8]}, "stub")
    assert 8 in result.usedInsightIds and "선수8" in result.body


@pytest.mark.parametrize("row", [insight(1, kind="UNSUPPORTED"), insight(1, facts={})])
def test_stub_fails_instead_of_skipping_unrenderable_required_fact(row):
    with pytest.raises(ArticleWriterError, match="필수 사실"):
        write_template({"insights": [row], "requiredInsightIds": [1]}, "stub")


def test_selected_pair_fact_keeps_wins_draws_and_losses():
    row = insight(1, kind="DUO_REUNITED", facts={
        "members": [{"name": "김응철"}, {"name": "전원재"}],
        "sameTeamMatches": 10, "sameTeamWins": 8, "sameTeamDraws": 0, "sameTeamLosses": 2,
    })
    result, _ = write_template({"insights": [row], "requiredInsightIds": [1]}, "stub")
    assert "김응철" in result.body and "전원재" in result.body
    assert "10경기에서 8승 0무 2패" in result.body


def test_selected_scoring_and_attendance_keep_schedule_units():
    rows = [insight(1, kind="SCORING_STREAK"), insight(2, kind="ATTENDANCE_STREAK")]
    result, _ = write_template({"insights": rows, "requiredInsightIds": [1, 2]}, "template")
    assert "3개 일정 연속 득점" in result.body and "3개 일정 연속 출전" in result.body
    assert "3주" not in result.body and "3주" not in result.title


def test_unselected_requests_keep_optional_selection_behavior():
    rows = [insight(i) for i in range(1, 11)]
    result, _ = write_template({"insights": rows}, "stub")
    assert set(result.usedInsightIds) == set(range(1, 11))  # 기존 기본형은 같은 종류 사실을 묶어서 쓴다.
    writer, calls = fake_writer([draft([1])])
    writer.write({"insights": [insight(1)]}, "configured-model")
    assert not any(m["content"] == REQUIRED_FACTS_PROMPT for m in calls[0]["messages"])
