"""전체 관리자 인증은 클럽 관리자 인증과 교차 사용할 수 없다."""
from datetime import datetime, timedelta, timezone

import jwt
import pytest

from app.core.config import settings
from app.core.superadmin import decode_superadmin_token, superadmin_login_limiter


@pytest.fixture(autouse=True)
def superadmin_auth_settings(monkeypatch):
    monkeypatch.setattr(settings, "SUPER_ADMIN_PIN", "7418")
    monkeypatch.setattr(settings, "SUPER_ADMIN_TOKEN_TTL_MIN", 120)
    monkeypatch.setattr(settings, "ADMIN_LOGIN_MAX_FAIL", 3)
    monkeypatch.setattr(settings, "ADMIN_LOGIN_LOCK_SEC", 60)
    superadmin_login_limiter.reset()
    yield
    superadmin_login_limiter.reset()


def _headers(token):
    return {"Authorization": f"Bearer {token}"}


def _token(**changes):
    now = datetime.now(timezone.utc)
    payload = {"sub": "superadmin", "role": "SUPER_ADMIN", "iat": now, "exp": now + timedelta(minutes=5)}
    payload.update(changes)
    return jwt.encode(payload, settings.SECRET_KEY, algorithm="HS256")


def test_superadmin_login_and_me_without_club(client):
    before = datetime.now(timezone.utc)
    response = client.post("/api/admin/auth", json={"password": "7418"})
    assert response.status_code == 200, response.text
    data = response.json()
    assert set(data) == {"accessToken", "tokenType", "expiresAt"}
    assert data["tokenType"] == "Bearer"
    assert decode_superadmin_token(data["accessToken"]).role == "SUPER_ADMIN"
    expires = datetime.fromisoformat(data["expiresAt"].replace("Z", "+00:00"))
    assert before + timedelta(minutes=119) < expires < before + timedelta(minutes=121)
    me = client.get("/api/admin/me", headers=_headers(data["accessToken"]))
    assert me.status_code == 200 and me.json() == {"role": "SUPER_ADMIN"}


def test_superadmin_pin_and_ttl_are_backend_configurable(client, monkeypatch):
    monkeypatch.setattr(settings, "SUPER_ADMIN_PIN", "9081")
    monkeypatch.setattr(settings, "SUPER_ADMIN_TOKEN_TTL_MIN", 7)
    wrong = client.post("/api/admin/auth", json={"password": "7418"})
    assert wrong.status_code == 401 and wrong.json()["error"]["code"] == "INVALID_PIN"
    response = client.post("/api/admin/auth", json={"password": "9081"})
    assert response.status_code == 200
    claims = jwt.decode(response.json()["accessToken"], settings.SECRET_KEY, algorithms=["HS256"])
    assert claims["exp"] - claims["iat"] == 7 * 60


def test_superadmin_login_failure_lock_is_separate_from_club_admin(client, make_club):
    api = make_club("superadmin-lock")
    for _ in range(settings.ADMIN_LOGIN_MAX_FAIL):
        response = client.post("/api/admin/auth", json={"password": "wrong"})
        assert response.status_code == 401 and response.json()["error"]["code"] == "INVALID_PIN"
    locked = client.post("/api/admin/auth", json={"password": "7418"})
    assert locked.status_code == 429 and locked.json()["error"]["code"] == "LOGIN_LOCKED"
    # 같은 접속지의 전체 관리자 잠금이 클럽 관리자 로그인까지 막지 않는다.
    club_login = api.post("/admin/auth", {"password": "7777"}, admin=False)
    assert club_login.status_code == 200


def test_successful_superadmin_login_resets_failed_attempts(client):
    for _ in range(settings.ADMIN_LOGIN_MAX_FAIL - 1):
        assert client.post("/api/admin/auth", json={"password": "wrong"}).status_code == 401
    assert client.post("/api/admin/auth", json={"password": "7418"}).status_code == 200
    for _ in range(settings.ADMIN_LOGIN_MAX_FAIL - 1):
        assert client.post("/api/admin/auth", json={"password": "wrong"}).status_code == 401
    assert client.post("/api/admin/auth", json={"password": "7418"}).status_code == 200


def test_superadmin_me_requires_bearer(client):
    response = client.get("/api/admin/me")
    assert response.status_code == 401 and response.json()["error"]["code"] == "SUPER_ADMIN_REQUIRED"
    assert client.get("/api/admin/me", headers={"Authorization": "Basic example"}).status_code == 401


def test_superadmin_me_rejects_expired_token(client):
    expired = _token(iat=datetime.now(timezone.utc) - timedelta(hours=1),
                     exp=datetime.now(timezone.utc) - timedelta(seconds=1))
    response = client.get("/api/admin/me", headers=_headers(expired))
    assert response.status_code == 401 and response.json()["error"]["code"] == "TOKEN_EXPIRED"


@pytest.mark.parametrize("token", ["invalid", "a.b.c", "", "null"])
def test_superadmin_me_rejects_malformed_token(client, token):
    assert client.get("/api/admin/me", headers=_headers(token)).status_code == 401


@pytest.mark.parametrize("claim", ["exp", "iat", "sub", "role"])
def test_superadmin_token_requires_security_claims(client, claim):
    now = datetime.now(timezone.utc)
    payload = {"sub": "superadmin", "role": "SUPER_ADMIN", "iat": now, "exp": now + timedelta(minutes=1)}
    payload.pop(claim)
    token = jwt.encode(payload, settings.SECRET_KEY, algorithm="HS256")
    response = client.get("/api/admin/me", headers=_headers(token))
    assert response.status_code == 401 and response.json()["error"]["code"] == "INVALID_TOKEN"


@pytest.mark.parametrize("changes", [{"role": "ADMIN"}, {"sub": "1"}, {"role": "USER"}])
def test_superadmin_token_requires_exact_identity(client, changes):
    response = client.get("/api/admin/me", headers=_headers(_token(**changes)))
    assert response.status_code == 401 and response.json()["error"]["code"] == "INVALID_TOKEN"


def test_superadmin_token_rejects_wrong_signature(client):
    now = datetime.now(timezone.utc)
    token = jwt.encode({"sub": "superadmin", "role": "SUPER_ADMIN", "iat": now,
                        "exp": now + timedelta(minutes=1)}, "different-signing-key-for-test-only", algorithm="HS256")
    response = client.get("/api/admin/me", headers=_headers(token))
    assert response.status_code == 401 and response.json()["error"]["code"] == "INVALID_TOKEN"


def test_club_admin_and_superadmin_tokens_are_not_interchangeable(client, make_club):
    api = make_club("superadmin-isolation")
    club_as_super = client.get("/api/admin/me", headers=_headers(api.token))
    assert club_as_super.status_code == 401 and club_as_super.json()["error"]["code"] == "INVALID_TOKEN"

    response = client.post("/api/admin/auth", json={"password": "7418"})
    token = response.json()["accessToken"]
    super_as_club = client.get(api.url("/admin/me"), headers=_headers(token))
    assert super_as_club.status_code == 401 and super_as_club.json()["error"]["code"] == "INVALID_TOKEN"
