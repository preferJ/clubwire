"""API Request DTO. JSON은 camelCase(memberId), 파이썬은 snake_case."""
from datetime import date
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints
from pydantic.alias_generators import to_camel


class CamelModel(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True, extra="forbid")


class AdminAuthRequest(CamelModel):
    password: str = Field(min_length=1, max_length=64, description="관리자 암호(PIN), 예: 7777")


class ChangePinRequest(CamelModel):
    new_password: str = Field(min_length=4, max_length=64)


class MemberCreate(CamelModel):
    name: str = Field(min_length=1, max_length=50)
    joined_at: date | None = None
    birth_year: int | None = Field(default=None, ge=1900, le=2100, description="출생연도(예: 1992)")
    profile_image_url: str | None = Field(default=None, max_length=500)
    display_order: int | None = None
    initial_rating: float | None = Field(default=None, gt=0, le=5000,
                                         description="시작 Rating(기존 기록 이관용). 비우면 클럽 설정 INITIAL_RATING")


class MemberUpdate(CamelModel):
    name: str | None = Field(default=None, max_length=50)
    joined_at: date | None = Field(default=None, description="가입일. null을 보내면 지움(안 보내면 그대로)")
    birth_year: int | None = Field(default=None, ge=1900, le=2100,
                                   description="출생연도(예: 1992). null을 보내면 지움(안 보내면 그대로)")
    profile_image_url: str | None = Field(default=None, max_length=500)
    display_order: int | None = None
    active: bool | None = None


class SessionCreate(CamelModel):
    session_date: date
    title: str | None = Field(default=None, max_length=100)
    location: str | None = Field(default=None, max_length=200)


class SessionUpdate(CamelModel):
    session_date: date | None = None
    title: str | None = Field(default=None, max_length=100)
    location: str | None = Field(default=None, max_length=200)


class AttendeesAdd(CamelModel):
    member_ids: list[int] = Field(min_length=1)


class GuestsAdd(CamelModel):
    count: int = Field(default=1, ge=1, le=20)
    names: list[str] | None = None


class TeamGenerateRequest(CamelModel):
    team_count: int = Field(ge=2, le=6)
    seed: int | None = Field(default=None, description="재현용 난수 시드(생략 시 무작위)")


class TeamConfirmRequest(CamelModel):
    generation_id: int


class AssignmentRequest(CamelModel):
    action: Literal["ADD", "MOVE", "REMOVE"]
    member_id: int | None = None
    guest_id: int | None = None
    guest_name: str | None = Field(default=None, max_length=50)
    to_team_id: int | None = None
    reason: str | None = Field(default=None, max_length=200)


class NextMatchRequest(CamelModel):
    team_a_id: int = Field(description="맞붙을 팀 1 (SESSION_TEAM_ID)")
    team_b_id: int = Field(description="맞붙을 팀 2 (SESSION_TEAM_ID)")
    duration_sec: int | None = Field(default=None, ge=10, le=7200, description="생략 시 설정값")


class GoalRequest(CamelModel):
    team_id: int = Field(description="점수를 얻는 팀(SESSION_TEAM_ID)")
    scorer_member_id: int | None = None
    assist_member_id: int | None = None
    own_goal: bool = False
    guest_goal: bool = False
    elapsed_sec: int | None = Field(default=None, ge=0, description="생략 시 서버 시간 기준")
    idempotency_key: str | None = Field(default=None, max_length=64)
    memo: str | None = Field(default=None, max_length=200)


class EventCancelRequest(CamelModel):
    memo: str | None = Field(default=None, max_length=200)


class MatchMemberRequest(CamelModel):
    member_id: int
    team_id: int


class ConfigUpdateRequest(CamelModel):
    values: dict[str, Any]


class TitleTypeCreate(CamelModel):
    title_code: str = Field(min_length=1, max_length=30, pattern=r"^[A-Z0-9_]+$")
    title_name: str = Field(min_length=1, max_length=50)
    period_type: Literal["WEEKLY", "SESSION"] = "WEEKLY"
    award_method: Literal["MANUAL", "AUTO"] = "MANUAL"
    auto_rule: Literal["TOP_GOALS", "TOP_ASSISTS", "TOP_WINS"] | None = None
    counts_as_mvp: bool = False
    display_order: int = 0


class TitleTypeUpdate(CamelModel):
    title_name: str | None = Field(default=None, max_length=50)
    active: bool | None = None
    display_order: int | None = None
    counts_as_mvp: bool | None = None


class TitleAwardRequest(CamelModel):
    title_code: str
    member_id: int
    session_id: int | None = None
    award_date: date | None = None
    note: str | None = Field(default=None, max_length=200)


class ArticleUpdate(CamelModel):
    title: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)]
    summary: Annotated[str, StringConstraints(strip_whitespace=True, max_length=500)]
    content: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=16000)]
    used_insight_ids: list[Annotated[int, Field(strict=True, gt=0)]] | None = Field(default=None, max_length=100)
