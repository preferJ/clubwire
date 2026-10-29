"""슈퍼관리자가 운영팀(CLUB)을 관리하는 요청. 경기의 A/B팀과는 별개다."""
from typing import Annotated

from pydantic import StringConstraints

from app.schemas.requests import CamelModel


ClubSlug = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=50,
                                          pattern=r"^[a-z0-9_-]+$")]
ClubName = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)]
AdminPin = Annotated[str, StringConstraints(min_length=4, max_length=64)]


class SuperAdminClubCreate(CamelModel):
    club_slug: ClubSlug
    club_name: ClubName
    admin_pin: AdminPin
    sport_type: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=20)] = "FUTSAL"
    timezone: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=50)] = "Asia/Seoul"


class SuperAdminClubUpdate(CamelModel):
    club_slug: ClubSlug | None = None
    club_name: ClubName | None = None
    admin_pin: AdminPin | None = None
    timezone: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=50)] | None = None
