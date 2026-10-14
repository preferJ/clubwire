"""Rating 관련 교체 가능 알고리즘 (순수 계산, DB 모름).

- ConfidenceStrategy     : 원천값(경기 수, 마지막 출전일) → Confidence(0.0~1.0)
- TeamStrengthStrategy   : 선수 Rating 목록 + 인원수 → Team Strength
- MatchRatingStrategy    : 경기 결과 → 선수별 Rating 변화량
"""
import math
from dataclasses import dataclass, field
from datetime import date
from typing import Any, Protocol

from app.core.club_config import ClubConfig


# ---------------------------------------------------------------- Confidence
class ConfidenceStrategy(Protocol):
    version: str

    def calculate(self, match_count: int, last_played_date: date | None, as_of: date | None, cfg: ClubConfig) -> float: ...

    def rating_multiplier(self, confidence: float, cfg: ClubConfig) -> float: ...


class DefaultConfidenceStrategy:
    """경기 수가 쌓일수록 1에 수렴, 장기 미출전 시 감쇠(Rating 자체는 깎지 않는다)."""

    version = "confidence_v1"

    def calculate(self, match_count: int, last_played_date: date | None, as_of: date | None, cfg: ClubConfig) -> float:
        scale = float(cfg["CONFIDENCE_MATCH_SCALE"])
        base = 1.0 - math.exp(-max(match_count, 0) / scale)
        if last_played_date and as_of:
            days = (as_of - last_played_date).days
            grace = int(cfg["CONFIDENCE_DECAY_GRACE_DAYS"])
            if days > grace:
                base *= math.exp(-(days - grace) / float(cfg["CONFIDENCE_DECAY_DAYS"]))
        return max(0.0, min(1.0, base))

    def rating_multiplier(self, confidence: float, cfg: ClubConfig) -> float:
        hi = float(cfg["CONFIDENCE_MULT_MAX"])
        lo = float(cfg["CONFIDENCE_MULT_MIN"])
        return hi - (hi - lo) * confidence


# ---------------------------------------------------------------- Team Strength
class TeamStrengthStrategy(Protocol):
    version: str

    def calculate_team_strength(self, player_ratings: list[float], player_count: int, cfg: ClubConfig) -> float: ...


class AverageTeamStrengthStrategy:
    """평균 Rating + 인원수 보정(HEADCOUNT_ADVANTAGE_FACTOR, 초기 0).

    player_ratings: Rating이 있는 멤버만(게스트 제외)
    player_count  : 실제 인원(게스트 포함)
    """

    version = "team_strength_avg_v1"

    def calculate_team_strength(self, player_ratings: list[float], player_count: int, cfg: ClubConfig) -> float:
        avg = sum(player_ratings) / len(player_ratings) if player_ratings else float(cfg["INITIAL_RATING"])
        return avg + float(cfg["HEADCOUNT_ADVANTAGE_FACTOR"]) * player_count


def average(values: list[float], default: float) -> float:
    return sum(values) / len(values) if values else default


# ---------------------------------------------------------------- Match Rating
@dataclass
class RatedPlayer:
    member_id: int
    rating: float
    confidence: float


@dataclass
class MatchRatingResult:
    deltas: dict[int, float]
    detail: dict[str, Any] = field(default_factory=dict)


class MatchRatingStrategy(Protocol):
    version: str

    def calculate(
        self,
        team_a: list[RatedPlayer],
        team_b: list[RatedPlayer],
        headcount_a: int,
        headcount_b: int,
        score_a: int,
        score_b: int,
        cfg: ClubConfig,
    ) -> MatchRatingResult: ...


def expected_score(strength_a: float, strength_b: float, scale: float) -> float:
    return 1.0 / (1.0 + 10 ** ((strength_b - strength_a) / scale))


class EloMatchRatingStrategy:
    """승/무/패만 사용(득점·도움·골득실은 Rating에 넣지 않음).

    team_delta = K × (actual − expected)
    player_delta = team_delta × multiplier(confidence)   (신규/복귀 선수는 크게, 안정 선수는 작게)
    """

    version = "match_elo_v1"

    def __init__(self, strength: TeamStrengthStrategy, confidence: ConfidenceStrategy):
        self.strength = strength
        self.confidence = confidence

    def calculate(
        self,
        team_a: list[RatedPlayer],
        team_b: list[RatedPlayer],
        headcount_a: int,
        headcount_b: int,
        score_a: int,
        score_b: int,
        cfg: ClubConfig,
    ) -> MatchRatingResult:
        s_a = self.strength.calculate_team_strength([p.rating for p in team_a], headcount_a, cfg)
        s_b = self.strength.calculate_team_strength([p.rating for p in team_b], headcount_b, cfg)
        exp_a = expected_score(s_a, s_b, float(cfg["RATING_EXPECTATION_SCALE"]))
        actual_a = 1.0 if score_a > score_b else 0.5 if score_a == score_b else 0.0
        k = float(cfg["MATCH_RATING_K"])
        team_delta_a = k * (actual_a - exp_a)
        team_delta_b = -team_delta_a

        deltas: dict[int, float] = {}
        mults: dict[int, float] = {}
        for p in team_a:
            m = self.confidence.rating_multiplier(p.confidence, cfg)
            mults[p.member_id] = m
            deltas[p.member_id] = team_delta_a * m
        for p in team_b:
            m = self.confidence.rating_multiplier(p.confidence, cfg)
            mults[p.member_id] = m
            deltas[p.member_id] = team_delta_b * m
        return MatchRatingResult(
            deltas=deltas,
            detail={
                "strengthA": s_a,
                "strengthB": s_b,
                "expectedA": exp_a,
                "actualA": actual_a,
                "k": k,
                "teamDeltaA": team_delta_a,
                "multipliers": {str(k_): v for k_, v in mults.items()},
            },
        )


# 기본 조합(교체 시 여기만 바꾼다)
confidence_strategy: ConfidenceStrategy = DefaultConfidenceStrategy()
team_strength_strategy: TeamStrengthStrategy = AverageTeamStrengthStrategy()
match_rating_strategy: MatchRatingStrategy = EloMatchRatingStrategy(team_strength_strategy, confidence_strategy)
