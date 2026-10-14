"""다음 경기 대진 '추천' (순수 계산).

대진은 항상 관리자가 정한다(2026-10-14 결정). 이 Strategy는 관리자 화면에 미리 채워 둘
기본값만 계산한다: 가장 오래 쉰 팀 두 팀.

  정렬 기준: 마지막 출전 경기 순번(오래될수록 먼저) → 오늘 경기 수(적을수록 먼저) → 팀 순서
  3팀이면 A-B → C-A → B-C → A-B … 처럼 돌아가며 맞붙는 순서가 된다.
"""
from dataclasses import dataclass, field


@dataclass
class PlayedMatch:
    team_a_id: int
    team_b_id: int


@dataclass
class TeamPlayStatus:
    team_id: int
    games: int
    consecutive: int
    last_index: int  # 마지막으로 뛴 경기의 순번(0부터), 안 뛰었으면 -1


@dataclass
class MatchSuggestion:
    team_a_id: int
    team_b_id: int
    teams: list[TeamPlayStatus] = field(default_factory=list)


class RestLongestSuggestionStrategy:
    version = "rest_longest_v1"

    def status(self, team_ids: list[int], history: list[PlayedMatch]) -> list[TeamPlayStatus]:
        out = []
        for t in team_ids:
            played = [i for i, m in enumerate(history) if t in (m.team_a_id, m.team_b_id)]
            consecutive = 0
            for m in reversed(history):
                if t in (m.team_a_id, m.team_b_id):
                    consecutive += 1
                else:
                    break
            out.append(TeamPlayStatus(t, len(played), consecutive, played[-1] if played else -1))
        return out

    def suggest(self, team_ids: list[int], history: list[PlayedMatch]) -> MatchSuggestion:
        if len(team_ids) < 2:
            raise ValueError("팀이 2개 이상이어야 합니다.")
        st = self.status(team_ids, history)
        order = {t: i for i, t in enumerate(team_ids)}
        ranked = sorted(st, key=lambda s: (s.last_index, s.games, order[s.team_id]))
        return MatchSuggestion(ranked[0].team_id, ranked[1].team_id, st)


match_order_strategy = RestLongestSuggestionStrategy()
