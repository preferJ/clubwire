"""관리자 인증.

MVP: 회원 로그인 없음. 클럽별 관리자 PIN(예: 7777)을 입력하면 관리자 토큰(JWT)을 발급한다.
- PIN은 Argon2 해시로만 저장한다.
- 4자리 PIN은 무차별 대입에 약하므로 (클럽, 접속지) 단위로 실패 횟수를 제한한다.
"""
import threading
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError

from app.core.config import settings
from app.core.errors import TooManyRequests, Unauthorized

_hasher = PasswordHasher()
_ALGO = "HS256"


def hash_password(raw: str) -> str:
    return _hasher.hash(raw)


def verify_password(password_hash: str, raw: str) -> bool:
    try:
        return _hasher.verify(password_hash, raw)
    except (VerifyMismatchError, VerificationError, InvalidHashError):
        return False


@dataclass
class AdminPrincipal:
    club_id: int
    admin_id: int


def create_admin_token(club_id: int, admin_id: int) -> tuple[str, datetime]:
    expires = datetime.now(timezone.utc) + timedelta(minutes=settings.ADMIN_TOKEN_TTL_MIN)
    payload = {"sub": str(admin_id), "club": club_id, "role": "ADMIN", "exp": expires}
    return jwt.encode(payload, settings.SECRET_KEY, algorithm=_ALGO), expires


def decode_admin_token(token: str) -> AdminPrincipal:
    try:
        data = jwt.decode(token, settings.SECRET_KEY, algorithms=[_ALGO])
    except jwt.ExpiredSignatureError as e:
        raise Unauthorized("관리자 인증이 만료되었습니다.", "TOKEN_EXPIRED") from e
    except jwt.PyJWTError as e:
        raise Unauthorized("관리자 인증이 올바르지 않습니다.", "INVALID_TOKEN") from e
    if data.get("role") != "ADMIN":
        raise Unauthorized("관리자 토큰이 아닙니다.", "INVALID_TOKEN")
    return AdminPrincipal(club_id=int(data["club"]), admin_id=int(data["sub"]))


class LoginRateLimiter:
    """메모리 기반 실패 횟수 제한(단일 프로세스 기준)."""

    def __init__(self) -> None:
        self._fails: dict[str, list[float]] = {}
        self._locked_until: dict[str, float] = {}
        self._lock = threading.Lock()

    def check(self, key: str) -> None:
        with self._lock:
            until = self._locked_until.get(key)
            if until and until > time.time():
                raise TooManyRequests(
                    f"PIN 입력 실패가 많아 {int(until - time.time())}초 동안 잠겼습니다.", "LOGIN_LOCKED"
                )

    def fail(self, key: str) -> None:
        now = time.time()
        with self._lock:
            window = [t for t in self._fails.get(key, []) if now - t < settings.ADMIN_LOGIN_LOCK_SEC]
            window.append(now)
            self._fails[key] = window
            if len(window) >= settings.ADMIN_LOGIN_MAX_FAIL:
                self._locked_until[key] = now + settings.ADMIN_LOGIN_LOCK_SEC
                self._fails[key] = []

    def success(self, key: str) -> None:
        with self._lock:
            self._fails.pop(key, None)
            self._locked_until.pop(key, None)

    def reset(self) -> None:
        with self._lock:
            self._fails.clear()
            self._locked_until.clear()


login_limiter = LoginRateLimiter()
