"""클럽별 엠블럼·기본 테마. 임의 SVG/HTML 대신 검증된 디자인 값만 저장한다."""
from typing import Annotated, Literal

from pydantic import StringConstraints

from app.schemas.requests import CamelModel


MAX_IMAGE_DATA_URL_LENGTH = 2_800_000  # 2MiB 이미지의 base64 + data URL 헤더
HexColor = Annotated[str, StringConstraints(pattern=r"^#[0-9a-fA-F]{6}$")]
CrestText = Annotated[str, StringConstraints(strip_whitespace=True, max_length=6,
                                           pattern=r"^[^\x00-\x1f\x7f<>]*$")]


class CrestConfig(CamelModel):
    mode: Literal["auto", "design", "image"] = "auto"
    shape: Literal["shield", "circle", "rounded"] = "shield"
    pattern: Literal["solid", "stripes", "diagonal"] = "stripes"
    primary_color: HexColor = "#c81e2b"
    secondary_color: HexColor = "#ffffff"
    text_color: HexColor = "#ffffff"
    text: CrestText = ""
    symbol: Literal["none", "ball", "star"] = "none"


class ClubAppearanceUpdate(CamelModel):
    crest: CrestConfig | None = None
    image_data_url: Annotated[str, StringConstraints(max_length=MAX_IMAGE_DATA_URL_LENGTH)] | None = None
    default_theme: Literal["dark", "light"] | None = None
