"""Insight Type 기준 데이터(INSIGHT_TYPE_CONFIG / INSIGHT_CONFIG_PARAM 초기값).

DB에 없을 때만 넣는다(운영 중 관리자가 바꾼 값은 덮어쓰지 않음).
"""
from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import InsightConfigParam, InsightTypeConfig


@dataclass(frozen=True)
class InsightTypeDef:
    insight_type: str
    category: str
    base: int
    max_imp: int
    pre: bool
    post: bool
    tag: str
    rule_version: str
    description: str
    params: dict[str, str] = field(default_factory=dict)
    min_imp: int = 0


MILESTONES = "10,30,50,100,150,200,300,500"

INSIGHT_TYPE_DEFS: tuple[InsightTypeDef, ...] = (
    InsightTypeDef("RETURN_PLAYER", "PLAYER", 40, 95, True, False, "복귀", "return_player_v1",
                   "N일 이상 미출전 후 복귀", {"threshold_days": "30", "max_days": "120"}),
    InsightTypeDef("RETURN_PLAYER_RESULT", "PLAYER", 45, 90, False, True, "복귀", "return_player_result_v1",
                   "복귀한 선수의 당일 결과", {"threshold_days": "30", "max_days": "120"}),
    InsightTypeDef("FIRST_APPEARANCE", "PLAYER", 50, 70, True, False, "데뷔", "first_appearance_v1",
                   "확정 경기 기록이 없는 선수의 첫 참석"),
    InsightTypeDef("WIN_STREAK", "STREAK", 50, 95, True, True, "연승", "win_streak_v1",
                   "연속 경기 승리", {"minimum_streak": "3", "importance_per_extra_win": "8"}),
    InsightTypeDef("SCORING_STREAK", "STREAK", 45, 90, True, True, "연속골", "scoring_streak_v1",
                   "연속 일정 득점", {"minimum_streak": "3", "importance_per_extra": "8"}),
    InsightTypeDef("MILESTONE_EXPECTED", "MILESTONE", 45, 85, True, False, "마일스톤", "milestone_expected_v1",
                   "오늘 달성 가능성이 있는 기록", {"milestones": MILESTONES, "games_gap": "3", "goals_gap": "2",
                                          "assists_gap": "2"}),
    InsightTypeDef("MILESTONE_ACHIEVED", "MILESTONE", 55, 95, False, True, "마일스톤", "milestone_achieved_v1",
                   "오늘 달성한 기록", {"milestones": MILESTONES}),
    InsightTypeDef("RARE_PAIR", "PAIR", 45, 85, True, False, "페어", "rare_pair_v1",
                   "함께 참석은 많았지만 같은 팀은 드물었던 조합",
                   {"min_co_attendance": "5", "max_same_team_ratio": "0.2", "min_sessions_since_same_team": "4",
                    "max_sessions_signal": "20"}),
    InsightTypeDef("CLOSE_MATCH_EXPECTED", "MATCH", 40, 70, True, False, "접전", "close_match_expected_v1",
                   "팀 간 전력이 매우 균형적", {"max_spread_percent": "1.0", "min_avg_match_count": "3"}),
    InsightTypeDef("LATE_WINNER", "MATCH", 60, 95, False, True, "결승골", "late_winner_v1",
                   "종료 직전 결승골", {"max_remaining_sec": "60"}),
    InsightTypeDef("COMEBACK_WIN", "MATCH", 60, 95, False, True, "역전", "comeback_win_v1",
                   "N골 이상 뒤지다 역전승", {"min_deficit": "2", "max_deficit_signal": "4"}),
    InsightTypeDef("UPSET_WIN", "MATCH", 55, 90, False, True, "이변", "upset_win_v1",
                   "경기 전 열세 예상 팀의 승리", {"max_expected": "0.4", "min_expected_signal": "0.2"}),
    InsightTypeDef("HAT_TRICK", "PLAYER", 65, 95, False, True, "해트트릭", "hat_trick_v1",
                   "한 경기 3골 이상", {"min_goals": "3"}),
    InsightTypeDef("TITLE_AWARDED", "TITLE", 50, 80, False, True, "타이틀", "title_awarded_v1",
                   "주간 타이틀 수여(자동 집계분)"),
    # ---- 2026-10-20 추가 (docs/DECISIONS.md 3-4) ----
    InsightTypeDef("DUO_REUNITED", "PAIR", 50, 85, True, False, "듀오", "duo_reunited_v1",
                   "같은 팀일 때 승률이 높은 두 선수가 다시 한 팀",
                   {"min_same_team_matches": "10", "min_win_rate": "0.65", "max_per_session": "3"}),
    InsightTypeDef("NEMESIS_MATCH", "PAIR", 50, 88, True, False, "천적", "nemesis_match_v1",
                   "맞대결에서 한쪽이 크게 앞선 두 선수가 다른 팀",
                   {"min_matches": "6", "min_win_rate": "0.7", "max_per_session": "3"}),
    InsightTypeDef("JINX_PAIR", "PAIR", 45, 75, True, False, "징크스", "jinx_pair_v1",
                   "같은 팀일 때 승률이 낮은 두 선수가 다시 한 팀",
                   {"min_same_team_matches": "10", "max_win_rate": "0.3", "max_per_session": "2"}),
    InsightTypeDef("SCORING_RACE", "RACE", 45, 80, True, False, "레이스", "scoring_race_v1",
                   "이달 득점 1·2위가 근소한 차이로 둘 다 출전",
                   {"max_gap": "2", "min_leader_goals": "3"}),
    InsightTypeDef("ATTENDANCE_STREAK", "STREAK", 40, 75, True, False, "개근", "attendance_streak_v1",
                   "연속 출전(일정 기준, 오늘 포함)", {"minimum_streak": "6", "importance_per_extra": "4"}),
    InsightTypeDef("REVENGE_RESULT", "PAIR", 55, 92, False, True, "천적", "revenge_result_v1",
                   "오늘 프리뷰의 천적 매치 두 선수가 실제로 맞붙은 결과"),
    InsightTypeDef("ASSIST_COMBO", "PAIR", 50, 85, False, True, "콤비", "assist_combo_v1",
                   "같은 도움→득점 조합이 오늘 여러 번", {"min_count": "2"}),
    InsightTypeDef("UNBEATEN_TEAM", "TEAM", 50, 85, False, True, "무패", "unbeaten_team_v1",
                   "오늘 N경기 이상 치르고 패배 없는 팀", {"min_games": "3", "max_games_signal": "8"}),
    InsightTypeDef("CLEAN_SHEET", "TEAM", 45, 80, False, True, "철벽", "clean_sheet_v1",
                   "오늘 N경기 이상 무실점한 팀", {"min_clean_sheets": "3", "max_signal": "6"}),
    InsightTypeDef("FIRST_GOAL", "PLAYER", 45, 70, False, True, "데뷔", "first_goal_v1",
                   "기록 집계 후 첫 골(클럽 첫 기록일 제외)"),
    InsightTypeDef("FIRST_ASSIST", "PLAYER", 40, 65, False, True, "데뷔", "first_assist_v1",
                   "기록 집계 후 첫 도움(클럽 첫 기록일 제외)"),
    InsightTypeDef("PERSONAL_BEST_GOALS", "PLAYER", 55, 90, False, True, "신기록", "personal_best_goals_v1",
                   "하루 득점이 본인 최다 기록을 넘음", {"min_goals": "3", "min_prior_sessions": "3"}),
)


def ensure_insight_types(db: Session) -> None:
    existing = set(db.scalars(select(InsightTypeConfig.insight_type)))
    existing_params = {(p.insight_type, p.param_key) for p in db.scalars(select(InsightConfigParam))}
    for d in INSIGHT_TYPE_DEFS:
        if d.insight_type not in existing:
            db.add(
                InsightTypeConfig(
                    insight_type=d.insight_type, category=d.category, enabled_yn=True,
                    base_importance=d.base, min_importance=d.min_imp, max_importance=d.max_imp,
                    pre_match_yn=d.pre, post_match_yn=d.post, tag_name=d.tag,
                    rule_version=d.rule_version, description=d.description,
                )
            )
    db.flush()
    for d in INSIGHT_TYPE_DEFS:
        for k, v in d.params.items():
            if (d.insight_type, k) not in existing_params:
                db.add(InsightConfigParam(insight_type=d.insight_type, param_key=k, param_value=v))
