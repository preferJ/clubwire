"""순수 알고리즘 단위 테스트(DB 불필요)."""
from datetime import date

import pytest

from app.core.club_config import ClubConfig
from app.integrations.openai.writer import ArticleWriterError, validate_draft
from app.strategies.match_order import PlayedMatch, match_order_strategy as mo
from app.strategies.rating import DefaultConfidenceStrategy, RatedPlayer, match_rating_strategy
from app.strategies.team_generation import MemberInput, spread_percent, team_generator, team_sizes

cfg = ClubConfig.defaults()


@pytest.mark.parametrize("n,k,expected", [(11, 2, [6, 5]), (13, 2, [7, 6]), (18, 3, [6, 6, 6]), (20, 3, [7, 7, 6])])
def test_team_sizes(n, k, expected):
    assert team_sizes(n, k) == expected


def test_spread():
    assert round(spread_percent([1004, 996]), 3) == 0.8


def test_pair_diversity_beats_perfect_balance():
    """§40: 허용 범위 안이면 Rating 차이 0보다 Pair 다양성을 우선."""
    members = [MemberInput(i, 1000.0, 0.5) for i in range(1, 9)]
    # 1-2, 3-4는 기회 10번 중 10번 같은 팀 → 같은 팀이면 큰 Penalty
    heavy = {(1, 2), (3, 4)}

    def lookup(a, b):
        return (10, 10) if (min(a, b), max(a, b)) in heavy else (0, 10)

    r = team_generator.generate(members, [], 2, lookup, cfg, seed=42)
    for t in r.teams:
        s = set(t.member_ids)
        assert not ({1, 2} <= s) and not ({3, 4} <= s)
    assert r.pair_penalty == 0


def test_tolerance_filters_unbalanced():
    members = [MemberInput(i, 1200.0 if i <= 3 else 900.0, 0.5) for i in range(1, 9)]
    r = team_generator.generate(members, [], 2, lambda a, b: (0, 0), cfg, seed=1)
    strong = [len([m for m in t.member_ids if m <= 3]) for t in r.teams]
    assert sorted(strong) == [1, 2]  # 강자 3명이 한 팀에 몰리지 않음


def test_confidence_and_decay():
    c = DefaultConfidenceStrategy()
    new = c.calculate(0, None, date(2026, 1, 1), cfg)
    vet = c.calculate(40, date(2026, 1, 1), date(2026, 1, 8), cfg)
    away = c.calculate(40, date(2026, 1, 1), date(2026, 6, 1), cfg)
    assert new == 0 and vet > 0.95 and away < vet
    assert c.rating_multiplier(new, cfg) > c.rating_multiplier(vet, cfg)


def test_elo_upset_moves_more():
    a = [RatedPlayer(1, 1000, 1.0)]
    b = [RatedPlayer(2, 1200, 1.0)]
    favorite_wins = match_rating_strategy.calculate(a, b, 5, 5, 0, 1, cfg).deltas[2]
    upset = match_rating_strategy.calculate(a, b, 5, 5, 1, 0, cfg).deltas[1]
    assert upset > favorite_wins > 0


def test_match_suggestion_rest_longest():
    t = [1, 2, 3]
    assert (mo.suggest(t, []).team_a_id, mo.suggest(t, []).team_b_id) == (1, 2)
    h = [PlayedMatch(1, 2)]
    assert (mo.suggest(t, h).team_a_id, mo.suggest(t, h).team_b_id) == (3, 1)  # 안 뛴 3 + 먼저인 1
    h.append(PlayedMatch(3, 1))
    assert (mo.suggest(t, h).team_a_id, mo.suggest(t, h).team_b_id) == (2, 3)
    h.append(PlayedMatch(2, 3))
    s = mo.suggest(t, h)
    assert (s.team_a_id, s.team_b_id) == (1, 2)  # A-B → C-A → B-C → A-B 순환
    assert {x.team_id: x.consecutive for x in s.teams} == {1: 0, 2: 1, 3: 2}


def test_ai_draft_validation():
    payload = {"insights": [{"id": 1}, {"id": 2}]}
    d = validate_draft({"title": "t", "summary": "s", "body": "b", "usedInsightIds": [2, 99, 2]}, payload)
    assert d.usedInsightIds == [2]
    with pytest.raises(ArticleWriterError):
        validate_draft({"title": "t", "summary": "s", "body": "Rating 1184로 앞선다", "usedInsightIds": []}, payload)


def test_openai_writer_structured_output(monkeypatch):
    """OpenAI 호출 형태(JSON Schema) + 응답 검증 + 금칙어 재시도."""
    import json
    from types import SimpleNamespace

    from app.core.config import settings
    from app.integrations.openai import writer as w

    monkeypatch.setattr(settings, "OPENAI_API_KEY", "sk-test")
    calls = []
    replies = [
        {"title": "t", "summary": "s", "body": "Rating이 높다", "usedInsightIds": [1]},  # 금칙어 → 재시도
        {"title": "돌아온 진선호", "summary": "30일 만의 복귀", "body": "본문", "usedInsightIds": [1, 7]},
    ]

    def create(**kw):
        calls.append(kw)
        content = json.dumps(replies[len(calls) - 1], ensure_ascii=False)
        return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=content))])

    wr = w.OpenAIArticleWriter()
    wr.client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))
    draft, raw = wr.write({"insights": [{"id": 1, "importance": 60}]}, "model-from-config")
    assert draft.title == "돌아온 진선호" and draft.usedInsightIds == [1]
    assert len(calls) == 2 and calls[0]["model"] == "model-from-config"
    assert calls[0]["response_format"]["json_schema"]["strict"] is True
    assert calls[0]["messages"][0]["role"] == "system"
