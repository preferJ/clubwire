"""클럽과 독립적인 전체 관리자 인증과 의존성."""
import hmac
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

import jwt
from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.core.config import settings
from app.core.errors import Unauthorized
from app.core.security import LoginRateLimiter

_ALGORITHM = "HS256"
_ROLE = "SUPER_ADMIN"
_SUBJECT = "superadmin"
_bearer = HTTPBearer(auto_error=False, scheme_name="SuperAdminBearer", description="전체 관리자 토큰")
superadmin_login_limiter = LoginRateLimiter()


@dataclass(frozen=True)
class SuperAdminPrincipal:
    role: str = _ROLE


def create_superadmin_token() -> tuple[str, datetime]:
    issued = datetime.now(timezone.utc)
    expires = issued + timedelta(minutes=settings.SUPER_ADMIN_TOKEN_TTL_MIN)
    payload = {"sub": _SUBJECT, "role": _ROLE, "iat": issued, "exp": expires}
    return jwt.encode(payload, settings.SECRET_KEY, algorithm=_ALGORITHM), expires


def decode_superadmin_token(token: str) -> SuperAdminPrincipal:
    try:
        data = jwt.decode(
            token, settings.SECRET_KEY, algorithms=[_ALGORITHM],
            options={"require": ["exp", "iat", "sub", "role"]},
        )
    except jwt.ExpiredSignatureError as e:
        raise Unauthorized("전체 관리자 인증이 만료되었습니다.", "TOKEN_EXPIRED") from e
    except jwt.PyJWTError as e:
        raise Unauthorized("전체 관리자 인증이 올바르지 않습니다.", "INVALID_TOKEN") from e
    if data.get("role") != _ROLE or data.get("sub") != _SUBJECT:
        raise Unauthorized("전체 관리자 토큰이 아닙니다.", "INVALID_TOKEN")
    return SuperAdminPrincipal()


def superadmin_login(password: str, client_key: str) -> tuple[str, datetime]:
    # 클럽 관리자 실패 횟수와 잠금 상태가 서로 영향을 주지 않는다.
    key = f"superadmin:{client_key}"
    superadmin_login_limiter.check(key)
    if not hmac.compare_digest(password.encode("utf-8"), settings.SUPER_ADMIN_PIN.encode("utf-8")):
        superadmin_login_limiter.fail(key)
        raise Unauthorized("전체 관리자 암호가 올바르지 않습니다.", "INVALID_PIN")
    superadmin_login_limiter.success(key)
    return create_superadmin_token()


def superadmin_dep(
    credential: HTTPAuthorizationCredentials | None = Depends(_bearer),
) -> SuperAdminPrincipal:
    if not credential:
        raise Unauthorized("전체 관리자 모드가 필요합니다.", "SUPER_ADMIN_REQUIRED")
    return decode_superadmin_token(credential.credentials)
