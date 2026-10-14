"""자동 팀 편성 (순수 계산).

우선순위(§40):
  1. Rating 허용 범위(TEAM_RATING_TOLERANCE_PERCENT)를 만족하는가
  2. 만족하는 후보 중 Pair 다양성(Pair Penalty 최소)
  3. Pair Penalty가 비슷하면(EPSILON 이내) Rating 균형이 더 좋은 후보
  4. 그래도 같으면 Random
Rating 차이 0을 추구하지 않는다.
"""
import random
import string
from collections.abc import Callable
from dataclasses import dataclass, field
from itertools import combinations
from typing import Any, Protocol

from app.core.club_config import ClubConfig
from app.strategies.rating import TeamStrengthStrategy

PairLookup = Callable[[int, int], tuple[int, int]]  # (member_a, member_b) -> (same_team_count, co_attendance_count)


# ---------------------------------------------------------------- Pair Penalty
class PairPenaltyStrategy(Protocol):
    version: str

    def pair_penalty(self, same_team_count: int, co_attendance_count: int, cfg: ClubConfig) -> float: ...


class SmoothedPairPenaltyStrategy:
    """같은 팀이 될 기회가 많았는데 실제로도 자주 같은 팀이었다면 Penalty가 높다.

    penalty = same_team_count / (co_attendance_count + alpha)
    """

    version = "pair_smooth_v1"

    def pair_penalty(self, same_team_count: int, co_attendance_count: int, cfg: ClubConfig) -> float:
        alpha = float(cfg["PAIR_ALPHA"])
        denom = co_attendance_count + alpha
        return same_team_count / denom if denom > 0 else 0.0


# ---------------------------------------------------------------- Team Generation
@dataclass
class MemberInput:
    member_id: int
    rating: float
    confidence: float


@dataclass
class GeneratedTeam:
    team_code: str
    member_ids: list[int]
    guest_ids: list[int]
    avg_rating: float
    strength: float
    headcount: int
    pair_penalty: float


@dataclass
class GenerationResult:
    teams: list[GeneratedTeam]
    spread_percent: float
    pair_penalty: float
    candidate_count: int
    valid_candidate_count: int
    tolerance_fallback: bool
    seed: int
    algorithm_version: str
    extra: dict[str, Any] = field(default_factory=dict)


def team_sizes(total: int, team_count: int) -> list[int]:
    """앞 remainder개 팀은 base+1, 나머지는 base. 팀별 인원 차이는 최대 1."""
    base, rem = divmod(total, team_count)
    return [base + 1 if i < rem else base for i in range(team_count)]


def spread_percent(strengths: list[float]) -> float:
    """(최고 − 최저) / 평균 × 100"""
    if not strengths:
        return 0.0
    mean = sum(strengths) / len(strengths)
    if mean == 0:
        return 0.0
    return (max(strengths) - min(strengths)) / mean * 100.0


@dataclass
class _Candidate:
    member_groups: list[list[MemberInput]]
    guest_groups: list[list[int]]
    strengths: list[float]
    avgs: list[float]
    team_penalties: list[float]
    spread: float
    penalty: float


class RandomCandidateTeamGenerator:
    """Randomized Candidate Generation + Scoring (MVP)."""

    version = "random_candidate_v1"

    def __init__(self, strength: TeamStrengthStrategy, pair: PairPenaltyStrategy):
        self.strength = strength
        self.pair = pair

    def generate(
        self,
        members: list[MemberInput],
        guest_ids: list[int],
        team_count: int,
        pair_lookup: PairLookup,
        cfg: ClubConfig,
        seed: int | None = None,
    ) -> GenerationResult:
        if team_count < 2:
            raise ValueError("team_count는 2 이상이어야 합니다.")
        total = len(members) + len(guest_ids)
        if total < team_count:
            raise ValueError("참석 인원이 팀 수보다 적습니다.")

        seed = seed if seed is not None else random.SystemRandom().randrange(1, 2**62)
        rng = random.Random(seed)
        sizes = team_sizes(total, team_count)
        n_candidates = int(cfg["TEAM_CANDIDATE_COUNT"])
        tolerance = float(cfg["TEAM_RATING_TOLERANCE_PERCENT"])
        eps = float(cfg["PAIR_PENALTY_EPSILON"])
        initial = float(cfg["INITIAL_RATING"])

        # Pair penalty 캐시
        penalty_cache: dict[tuple[int, int], float] = {}
        for a, b in combinations(sorted(m.member_id for m in members), 2):
            same, co = pair_lookup(a, b)
            penalty_cache[(a, b)] = self.pair.pair_penalty(same, co, cfg)

        def team_penalty(group: list[MemberInput]) -> float:
            ids = sorted(m.member_id for m in group)
            return sum(penalty_cache.get((a, b), 0.0) for a, b in combinations(ids, 2))

        candidates: list[_Candidate] = []
        for _ in range(n_candidates):
            # 게스트는 팀에 고르게 분산(팀 순서는 매번 섞음)
            order = list(range(team_count))
            rng.shuffle(order)
            order.sort(key=lambda i: -sizes[i])  # 큰 팀부터(동률은 섞인 순서 유지)
            guest_groups: list[list[int]] = [[] for _ in range(team_count)]
            for gi, gid in enumerate(guest_ids):
                guest_groups[order[gi % team_count]].append(gid)
            slots = [sizes[i] - len(guest_groups[i]) for i in range(team_count)]
            if any(s < 0 for s in slots):
                continue
            shuffled = members[:]
            rng.shuffle(shuffled)
            groups: list[list[MemberInput]] = []
            pos = 0
            for s in slots:
                groups.append(shuffled[pos:pos + s])
                pos += s

            avgs, strengths, penalties = [], [], []
            for i, g in enumerate(groups):
                ratings = [m.rating for m in g]
                avgs.append(sum(ratings) / len(ratings) if ratings else initial)
                strengths.append(self.strength.calculate_team_strength(ratings, sizes[i], cfg))
                penalties.append(team_penalty(g))
            candidates.append(
                _Candidate(groups, guest_groups, strengths, avgs, penalties, spread_percent(strengths), sum(penalties))
            )

        valid = [c for c in candidates if c.spread <= tolerance + 1e-9]
        fallback = not valid
        if fallback:
            # 허용 범위를 만족하는 후보가 없으면 Rating 균형이 가장 좋은 후보군에서 선택
            best_spread = min(c.spread for c in candidates)
            pool = [c for c in candidates if c.spread <= best_spread + 1e-9]
        else:
            pool = valid

        min_penalty = min(c.penalty for c in pool)
        near = [c for c in pool if c.penalty <= min_penalty + eps]
        best_spread = min(c.spread for c in near)
        finalists = [c for c in near if c.spread <= best_spread + 1e-9]
        chosen = rng.choice(finalists)

        codes = string.ascii_uppercase
        teams = [
            GeneratedTeam(
                team_code=codes[i],
                member_ids=[m.member_id for m in chosen.member_groups[i]],
                guest_ids=chosen.guest_groups[i],
                avg_rating=chosen.avgs[i],
                strength=chosen.strengths[i],
                headcount=sizes[i],
                pair_penalty=chosen.team_penalties[i],
            )
            for i in range(team_count)
        ]
        return GenerationResult(
            teams=teams,
            spread_percent=chosen.spread,
            pair_penalty=chosen.penalty,
            candidate_count=len(candidates),
            valid_candidate_count=len(valid),
            tolerance_fallback=fallback,
            seed=seed,
            algorithm_version=self.version,
            extra={"pairStrategy": self.pair.version, "strengthStrategy": self.strength.version, "sizes": sizes},
        )


def balance_label(spread: float) -> str:
    """사용자에게 Rating 숫자 대신 보여줄 해석 문구."""
    if spread <= 1.0:
        return "팀 간 전력이 매우 균형적입니다."
    if spread <= 3.0:
        return "팀 간 전력이 비교적 균형적입니다."
    return "팀 간 전력 차이가 다소 있습니다."


def _default_generator() -> RandomCandidateTeamGenerator:
    from app.strategies.rating import team_strength_strategy

    return RandomCandidateTeamGenerator(team_strength_strategy, SmoothedPairPenaltyStrategy())


pair_penalty_strategy: PairPenaltyStrategy = SmoothedPairPenaltyStrategy()
team_generator = _default_generator()
