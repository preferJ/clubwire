"""클럽별 외형 저장과 정적 이미지 검증. 이미지는 파일 경로 없이 DB에 보관한다."""
import base64
import binascii
import hashlib
import struct
import warnings
import zlib
from datetime import timedelta
from io import BytesIO
from urllib.parse import quote

from PIL import Image, ImageOps, UnidentifiedImageError
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.database import emit
from app.core.errors import BadRequest, NotFound
from app.core.timeutil import to_iso, utcnow
from app.models import Club
from app.schemas.appearance import ClubAppearanceUpdate, CrestConfig


MAX_IMAGE_BYTES = 2 * 1024 * 1024
MAX_IMAGE_DIMENSION = 4096
MAX_IMAGE_PIXELS = 16_000_000
MAX_STORED_IMAGE_DIMENSION = 512
_IMAGE_MIME = {"PNG": "image/png", "JPEG": "image/jpeg", "WEBP": "image/webp"}


def _crest_config(club: Club) -> CrestConfig:
    try:
        return CrestConfig.model_validate(club.crest_config or {})
    except ValidationError:
        # 잘못 저장된 과거 설정 하나 때문에 클럽의 공개 조회를 막지 않는다.
        return CrestConfig()


def image_digest(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def serialize_appearance(club: Club) -> dict:
    crest = _crest_config(club)
    image_url = None
    if crest.mode == "image":
        if club.crest_image:
            version = image_digest(club.crest_image)[:16]
            image_url = f"/api/clubs/{quote(club.club_slug, safe='')}/appearance/crest?v={version}"
        else:
            # 이미지 없는 손상된 설정은 기존 자동 엠블럼으로 표시한다.
            crest = CrestConfig()
    return {
        "crest": crest.model_dump(by_alias=True),
        "imageUrl": image_url,
        "defaultTheme": club.default_theme if club.default_theme in ("dark", "light") else "dark",
        "updatedAt": to_iso(club.appearance_updated_at),
    }


def normalize_crest_image(data_url: str) -> bytes:
    """실제 이미지 내용을 검사하고 크기·메타데이터를 정규화한 PNG만 반환한다."""
    if not isinstance(data_url, str):
        raise BadRequest("올바른 엠블럼 이미지를 선택하세요.", "INVALID_CREST_IMAGE")
    header, separator, encoded = data_url.partition(",")
    allowed_headers = {f"data:{mime};base64": mime for mime in _IMAGE_MIME.values()}
    if not separator or header not in allowed_headers:
        raise BadRequest("PNG, JPEG, WebP 이미지만 사용할 수 있습니다.", "INVALID_CREST_IMAGE")
    if len(encoded) > ((MAX_IMAGE_BYTES + 2) // 3) * 4:
        raise BadRequest("엠블럼 이미지는 2MiB 이하여야 합니다.", "CREST_IMAGE_TOO_LARGE")
    try:
        content = base64.b64decode(encoded, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise BadRequest("이미지 데이터가 올바르지 않습니다.", "INVALID_CREST_IMAGE") from exc
    if not content:
        raise BadRequest("비어 있는 이미지는 사용할 수 없습니다.", "INVALID_CREST_IMAGE")
    if len(content) > MAX_IMAGE_BYTES:
        raise BadRequest("엠블럼 이미지는 2MiB 이하여야 합니다.", "CREST_IMAGE_TOO_LARGE")

    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(BytesIO(content)) as source:
                if source.format not in _IMAGE_MIME or _IMAGE_MIME[source.format] != allowed_headers[header]:
                    raise BadRequest("이미지 내용과 파일 형식이 일치하지 않습니다.", "INVALID_CREST_IMAGE")
                width, height = source.size
                if (width < 1 or height < 1 or width > MAX_IMAGE_DIMENSION or height > MAX_IMAGE_DIMENSION
                        or width * height > MAX_IMAGE_PIXELS):
                    raise BadRequest("이미지는 가로·세로 4096px 이하, 총 1600만 화소 이하여야 합니다.",
                                     "CREST_IMAGE_DIMENSIONS")
                if getattr(source, "is_animated", False):
                    raise BadRequest("움직이는 이미지는 엠블럼으로 사용할 수 없습니다.", "ANIMATED_CREST_IMAGE")
                source.verify()
            # verify 후 파일을 다시 열어 실제 픽셀도 끝까지 디코딩한다.
            with Image.open(BytesIO(content)) as source:
                oriented = ImageOps.exif_transpose(source)
                oriented.thumbnail((MAX_STORED_IMAGE_DIMENSION, MAX_STORED_IMAGE_DIMENSION), Image.Resampling.LANCZOS)
                normalized = oriented.convert("RGBA")
                clean = Image.new("RGBA", normalized.size)
                clean.paste(normalized)
                output = BytesIO()
                clean.save(output, format="PNG")
                return output.getvalue()
    except BadRequest:
        raise
    except (UnidentifiedImageError, OSError, EOFError, SyntaxError, ValueError, TypeError, OverflowError,
            struct.error, zlib.error, Image.DecompressionBombError,
            Image.DecompressionBombWarning) as exc:
        raise BadRequest("이미지를 읽을 수 없습니다. 다른 이미지 파일을 선택하세요.", "INVALID_CREST_IMAGE") from exc


def update_appearance(db: Session, club_id: int, changes: dict) -> Club:
    try:
        body = ClubAppearanceUpdate.model_validate(changes)
    except ValidationError as exc:
        raise BadRequest("엠블럼 또는 테마 설정이 올바르지 않습니다.", "INVALID_CLUB_APPEARANCE") from exc
    fields = body.model_fields_set
    # 이미지는 null로 삭제한다. 나머지 설정은 생략과 혼동하지 않도록 null을 거부한다.
    if any(field in fields and getattr(body, field) is None for field in ("crest", "default_theme")):
        raise BadRequest("엠블럼 설정과 기본 테마에는 null을 사용할 수 없습니다.", "INVALID_CLUB_APPEARANCE")
    # 이미지 디코딩은 행을 잠그거나 값을 변경하기 전에 끝낸다.
    replacement_image = (normalize_crest_image(body.image_data_url) if body.image_data_url is not None else None)
    club = db.scalar(select(Club).where(Club.club_id == club_id, Club.active_yn.is_(True)).with_for_update())
    if club is None:
        raise NotFound("클럽을 찾을 수 없습니다.", "CLUB_NOT_FOUND")

    crest = body.crest if "crest" in fields else _crest_config(club)
    image = replacement_image if "image_data_url" in fields else club.crest_image
    theme = body.default_theme if "default_theme" in fields else (club.default_theme or "dark")
    if crest.mode == "image" and not image:
        raise BadRequest("이미지 엠블럼을 사용하려면 이미지 파일을 먼저 선택하세요.", "CREST_IMAGE_REQUIRED")

    changed = False
    try:
        config = crest.model_dump(by_alias=True)
        if "crest" in fields and config != _crest_config(club).model_dump(by_alias=True):
            club.crest_config = config
            changed = True
        if "image_data_url" in fields and image != club.crest_image:
            club.crest_image = image
            changed = True
        if "default_theme" in fields and theme != (club.default_theme or "dark"):
            club.default_theme = theme
            changed = True
        if changed:
            now = utcnow()
            changed_at = now.replace(microsecond=(now.microsecond // 1000) * 1000)
            if club.appearance_updated_at is not None and changed_at <= club.appearance_updated_at:
                changed_at = club.appearance_updated_at + timedelta(milliseconds=1)
            club.appearance_updated_at = changed_at
            emit(db, club_id, "CLUB_APPEARANCE_UPDATED", {})
        db.commit()
    except Exception:
        db.rollback()
        raise
    return club


def crest_image(club: Club) -> bytes:
    """현재 공개 중인 이미지 엠블럼만 제공한다. 비활성 클럽은 club_dep에서 차단한다."""
    if _crest_config(club).mode != "image" or not club.crest_image:
        raise NotFound("이미지 엠블럼을 찾을 수 없습니다.", "CREST_IMAGE_NOT_FOUND")
    return club.crest_image
