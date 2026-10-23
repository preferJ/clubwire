"""SYSTEM_CONFIG 키 정의(타입, 기본값, 허용값).

- 실제 값의 원본은 DB(SYSTEM_CONFIG, 클럽별)다. 클럽 생성 시 아래 기본값으로 행을 만든다.
- 코드에는 '키의 정의'만 있고, 계산 로직은 ClubConfig를 통해 DB 값을 읽는다.
"""
from dataclasses import dataclass, field
from typing import Any

from app.core.errors import BadRequest


@dataclass(frozen=True)
class ConfigDef:
    key: str
    value_type: str  # INT | FLOAT | BOOL | STRING
    default: Any
    description: str
    choices: tuple[str, ...] = field(default_factory=tuple)
    min_value: float | None = None
    max_value: float | None = None


CONFIG_DEFS: tuple[ConfigDef, ...] = (
    # ---- Rating ----
    ConfigDef("INITIAL_RATING", "FLOAT", 1000.0, "신규 선수 초기 Rating", min_value=1),
    ConfigDef("MATCH_RATING_K", "FLOAT", 20.0, "경기 결과 Rating 변화 K", min_value=0),
    ConfigDef("RATING_EXPECTATION_SCALE", "FLOAT", 400.0, "Elo 기대승률 scale", min_value=1),
    ConfigDef("HEADCOUNT_ADVANTAGE_FACTOR", "FLOAT", 0.0, "팀 인원 1명당 Team Strength 가산(초기 0)"),
    # ---- Confidence ----
    ConfigDef("CONFIDENCE_MATCH_SCALE", "FLOAT", 10.0, "경기 수에 따른 Confidence 상승 속도(클수록 느림)", min_value=0.1),
    ConfigDef("CONFIDENCE_DECAY_GRACE_DAYS", "INT", 30, "미출전 후 Confidence 감소가 시작되는 일수", min_value=0),
    ConfigDef("CONFIDENCE_DECAY_DAYS", "FLOAT", 90.0, "미출전 Confidence 감쇠 시간상수(일)", min_value=1),
    ConfigDef("CONFIDENCE_MULT_MAX", "FLOAT", 2.0, "Confidence 0일 때 Rating 변화 배수", min_value=0),
    ConfigDef("CONFIDENCE_MULT_MIN", "FLOAT", 0.5, "Confidence 1일 때 Rating 변화 배수", min_value=0),
    # ---- Team Generation ----
    ConfigDef("TEAM_RATING_TOLERANCE_PERCENT", "FLOAT", 1.0, "팀 Strength 허용 차이(%) = (최고-최저)/평균", min_value=0),
    ConfigDef("TEAM_CANDIDATE_COUNT", "INT", 3000, "팀 편성 후보 생성 수", min_value=1, max_value=50000),
    ConfigDef("PAIR_ALPHA", "FLOAT", 2.0, "Pair Penalty smoothing alpha", min_value=0),
    ConfigDef("PAIR_PENALTY_EPSILON", "FLOAT", 0.01, "Pair Penalty가 이 차이 이내면 동점으로 보고 Rating 균형 비교", min_value=0),
    # ---- Match ----
    ConfigDef("MATCH_DURATION_SEC", "INT", 600, "경기 시간(초)", min_value=10),
    ConfigDef("MATCH_AUTO_END_YN", "BOOL", True, "시간 종료 시 자동 종료 여부(관리자 END는 항상 가능)"),
    ConfigDef("MATCH_EARLY_END_GOALS", "INT", 0, "한 팀이 N골에 도달하면 조기 종료(0=사용 안 함)", min_value=0),
    # ---- The Wire ----
    ConfigDef(
        "ARTICLE_PUBLISH_MODE", "STRING", "MANUAL", "기사 게시 방식: MANUAL=관리자 검토 후 게시, AUTO=생성 즉시 게시",
        choices=("MANUAL", "AUTO"),
    ),
    ConfigDef("WIRE_MAX_INSIGHTS", "INT", 15, "기사 1건에 AI로 넘기는 Insight 최대 개수", min_value=1, max_value=50),
    # ---- 이달의 MVP ----
    ConfigDef("MONTHLY_MVP_MIN_SESSIONS", "INT", 2, "이달의 MVP 후보 자격: 그 달 출전한 일정 수(이상)",
              min_value=1, max_value=31),
)

CONFIG_DEF_MAP: dict[str, ConfigDef] = {d.key: d for d in CONFIG_DEFS}


def parse_value(d: ConfigDef, raw: Any) -> Any:
    try:
        if d.value_type == "INT":
            v: Any = int(float(raw))
        elif d.value_type == "FLOAT":
            v = float(raw)
        elif d.value_type == "BOOL":
            if isinstance(raw, bool):
                v = raw
            else:
                s = str(raw).strip().upper()
                if s in ("TRUE", "Y", "1", "YES"):
                    v = True
                elif s in ("FALSE", "N", "0", "NO"):
                    v = False
                else:
                    raise ValueError(raw)
        else:
            v = str(raw)
    except (TypeError, ValueError) as e:
        raise BadRequest(f"{d.key} 값 형식이 올바르지 않습니다: {raw}", "INVALID_CONFIG") from e
    if d.choices and v not in d.choices:
        raise BadRequest(f"{d.key}는 {', '.join(d.choices)} 중 하나여야 합니다.", "INVALID_CONFIG")
    if d.min_value is not None and isinstance(v, (int, float)) and not isinstance(v, bool) and v < d.min_value:
        raise BadRequest(f"{d.key}는 {d.min_value} 이상이어야 합니다.", "INVALID_CONFIG")
    if d.max_value is not None and isinstance(v, (int, float)) and not isinstance(v, bool) and v > d.max_value:
        raise BadRequest(f"{d.key}는 {d.max_value} 이하여야 합니다.", "INVALID_CONFIG")
    return v


def serialize_value(d: ConfigDef, v: Any) -> str:
    if d.value_type == "BOOL":
        return "TRUE" if v else "FALSE"
    return str(v)


class ClubConfig:
    """클럽의 유효 설정값(타입 변환 완료) + 설정 버전."""

    def __init__(self, values: dict[str, Any], version: int):
        self._values = values
        self.version = version

    def __getitem__(self, key: str) -> Any:
        return self._values[key]

    def get(self, key: str, default: Any = None) -> Any:
        return self._values.get(key, default)

    def snapshot(self) -> dict[str, Any]:
        return dict(self._values)

    @classmethod
    def defaults(cls) -> "ClubConfig":
        return cls({d.key: d.default for d in CONFIG_DEFS}, version=0)
