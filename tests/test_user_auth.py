"""OAuth는 모의 카카오 응답으로, 계정 연결·CSRF·승인은 실제 테스트 DB/API로 확인."""
from datetime import datetime, timedelta, timezone
from urllib.parse import parse_qs, urlsplit

import httpx
import jwt
import pytest
from fastapi.testclient import TestClient

from app.core.config import settings
from app.core.database import SessionLocal
from app.core.timeutil import utcnow
from app.main import app
from app.models import AppUser, Member, MemberAccountLink
from app.services import user_auth_service as auth
from app.services.common import get_club_by_slug


def user_headers(kakao_id):
    with SessionLocal() as db:
        user = AppUser(kakao_id=kakao_id, nickname=f"회원 {kakao_id}")
        db.add(user)
        db.commit()
        token, csrf = auth.create_user_token(user)
        return user.user_id, {"Cookie": f"{auth.USER_COOKIE}={token}", "X-CSRF-Token": csrf}


def configure(monkeypatch, https=False):
    monkeypatch.setattr(settings, "KAKAO_CLIENT_ID", "test-client")
    monkeypatch.setattr(settings, "KAKAO_CLIENT_SECRET", "test-secret")
    monkeypatch.setattr(settings, "KAKAO_REDIRECT_URI",
                        "https://prefer.tail4eaf9e.ts.net/api/auth/kakao/callback" if https
                        else "http://localhost/api/auth/kakao/callback")


def test_oauth_roundtrip_cookie_and_no_provider_tokens(make_club, monkeypatch):
    make_club("oauth1")
    configure(monkeypatch)
    called = []

    class Kakao:
        def __init__(self, **kwargs):
            assert kwargs == {"timeout": 10, "follow_redirects": False}
        def __enter__(self): return self
        def __exit__(self, *_): pass
        def post(self, url, data):
            called.append(url)
            assert data["code"] == "test-code" and data["client_secret"] == "test-secret"
            assert data["redirect_uri"] == settings.KAKAO_REDIRECT_URI
            return httpx.Response(200, request=httpx.Request("POST", url), json={"access_token": "provider-secret"})
        def get(self, url, headers):
            called.append(url)
            assert headers == {"Authorization": "Bearer provider-secret"}
            return httpx.Response(200, request=httpx.Request("GET", url),
                                  json={"id": 810001, "properties": {"nickname": "카카오 이름"}})

    monkeypatch.setattr(auth.httpx, "Client", Kakao)
    # TestClient는 httpx.Client의 이미 정의된 subclass이므로 제공자용 생성자만 대체한다.
    client = TestClient(app, base_url="http://localhost")
    begin = client.get("/api/auth/kakao/login?clubSlug=oauth1", follow_redirects=False)
    assert begin.status_code == 302 and begin.headers["cache-control"] == "no-store"
    location = urlsplit(begin.headers["location"])
    assert location.netloc == "kauth.kakao.com"
    state = parse_qs(location.query)["state"][0]
    callback = client.get("/api/auth/kakao/callback", params={"state": state, "code": "test-code"}, follow_redirects=False)
    assert callback.status_code == 303 and callback.headers["location"] == "/c/oauth1/account?login=success"
    assert len(called) == 2
    assert "provider-secret" not in str(callback.headers) and "test-code" not in callback.headers["location"]
    assert "httponly" in callback.headers.get_list("set-cookie")[0].lower()
    assert auth.STATE_COOKIE not in client.cookies
    me = client.get("/api/auth/me").json()
    assert me["user"]["nickname"] == "카카오 이름" and len(me["csrfToken"]) > 20
    assert "kakaoId" not in me["user"]
    assert client.post("/api/auth/logout").status_code == 403
    old_token = client.cookies[auth.USER_COOKIE]
    assert client.post("/api/auth/logout", headers={"X-CSRF-Token": me["csrfToken"]}).status_code == 200
    assert client.get("/api/auth/me", headers={"Cookie": f"{auth.USER_COOKIE}={old_token}"}).json()["user"] is None


def test_oauth_state_errors_never_exchange_code(make_club, monkeypatch):
    make_club("oauth2")
    configure(monkeypatch, https=True)
    monkeypatch.setattr(auth, "exchange_kakao", lambda _: pytest.fail("invalid state exchanged"))
    client = TestClient(app, base_url="https://testserver")
    begin = client.get("/api/auth/kakao/login?clubSlug=oauth2", follow_redirects=False)
    assert "secure" in begin.headers["set-cookie"].lower()
    state = parse_qs(urlsplit(begin.headers["location"]).query)["state"][0]
    bad = client.get("/api/auth/kakao/callback?state=wrong&code=secret", follow_redirects=False)
    assert bad.headers["location"] == "/?login=failed" and auth.STATE_COOKIE not in client.cookies
    # 정확한 state도 브라우저의 state cookie가 없으면 실패
    missing = client.get("/api/auth/kakao/callback", params={"state": state, "code": "secret"}, follow_redirects=False)
    assert missing.headers["location"] == "/?login=failed"
    expired = jwt.encode({"role": "KAKAO_STATE", "state": "x", "club": "oauth2",
                          "exp": datetime.now(timezone.utc) - timedelta(seconds=1)}, settings.SECRET_KEY, algorithm="HS256")
    client.cookies.set(auth.STATE_COOKIE, expired)
    assert client.get("/api/auth/kakao/callback?state=x&code=secret", follow_redirects=False).headers["location"] == "/?login=failed"
    # 사용자 동의 취소: 유효 state를 확인하되 토큰 교환은 하지 않는다
    client.cookies.clear()
    begin = client.get("/api/auth/kakao/login?clubSlug=oauth2", follow_redirects=False)
    state = parse_qs(urlsplit(begin.headers["location"]).query)["state"][0]
    cancelled = client.get("/api/auth/kakao/callback", params={"state": state, "error": "access_denied"}, follow_redirects=False)
    assert cancelled.headers["location"] == "/c/oauth2/account?login=failed"


def test_oauth_configuration_and_provider_failure(make_club, monkeypatch):
    api = make_club("oauth3")
    monkeypatch.setattr(settings, "KAKAO_CLIENT_ID", None)
    c = TestClient(app)
    assert c.get("/api/auth/me").json()["configured"] is False
    assert c.get("/api/auth/kakao/login?clubSlug=oauth3", follow_redirects=False).status_code == 400
    configure(monkeypatch)
    for uri in ("http://example.com/api/auth/kakao/callback", "https://example.com/other", "https://example.com/api/auth/kakao/callback?next=https://evil.test"):
        monkeypatch.setattr(settings, "KAKAO_REDIRECT_URI", uri)
        assert auth.oauth_configured() is False
    configure(monkeypatch)
    begin = c.get("/api/auth/kakao/login?clubSlug=oauth3", follow_redirects=False)
    state = parse_qs(urlsplit(begin.headers["location"]).query)["state"][0]
    from app.core.errors import Unauthorized
    def failed(_): raise Unauthorized("provider failed")
    monkeypatch.setattr(auth, "exchange_kakao", failed)
    # http://testserver이지만 dev 설정은 localhost. state cookie Secure가 아니므로 왕복 가능.
    r = c.get("/api/auth/kakao/callback", params={"state": state, "code": "secret"}, follow_redirects=False)
    assert r.headers["location"] == "/c/oauth3/account?login=failed"
    assert auth.USER_COOKIE not in c.cookies


def test_link_request_approval_and_revoke_are_scoped(make_club):
    api = make_club("acct1")
    other = make_club("acct2")
    member = api.ok(api.post("/members", {"name": "선수"}), 201)["memberId"]
    foreign = other.ok(other.post("/members", {"name": "다른 선수"}), 201)["memberId"]
    uid, h = user_headers("820001")
    uid2, h2 = user_headers("820002")
    client = TestClient(app)
    path = api.url("/account/link")
    assert client.post(path, json={"memberId": member}).status_code == 401
    assert client.post(path, json={"memberId": member}, headers={"Cookie": h["Cookie"]}).status_code == 403
    assert client.post(path, json={"memberId": foreign}, headers=h).status_code == 404
    r = client.post(path, json={"memberId": member}, headers=h)
    assert r.status_code == 200 and r.json()["link"] is None and r.json()["request"]["status"] == "PENDING"
    request_id = r.json()["request"]["requestId"]
    assert client.post(path, json={"memberId": member}, headers=h).json()["request"]["requestId"] == request_id
    request2 = client.post(path, json={"memberId": member}, headers=h2).json()["request"]["requestId"]
    assert client.get(api.url("/admin/accounts"), headers=h).status_code == 401
    assert other.post(f"/admin/accounts/{request_id}/approve").status_code == 404
    api.ok(api.post(f"/admin/accounts/{request_id}/approve"))
    assert api.post(f"/admin/accounts/{request2}/approve").status_code == 409
    account = client.get(api.url("/account"), headers=h).json()
    assert account["link"] == {"memberId": member, "name": "선수"}
    with SessionLocal() as db:
        club = get_club_by_slug(db, api.slug)
        assert auth.approved_member(db, club.club_id, uid).member_id == member
        assert auth.approved_member(db, club.club_id, uid2) is None
    link_id = api.ok(api.get("/admin/accounts"))["links"][0]["linkId"]
    assert other.delete(f"/admin/accounts/{link_id}").status_code == 404
    api.ok(api.delete(f"/admin/accounts/{link_id}"))
    account = client.get(api.url("/account"), headers=h).json()
    assert account["link"] is None and account["request"]["status"] == "REVOKED"
    with SessionLocal() as db:
        assert auth.approved_member(db, club.club_id, uid) is None


def test_link_reject_cancel_and_user_token_cannot_be_admin(make_club):
    api = make_club("acct3")
    member = api.ok(api.post("/members", {"name": "선수"}), 201)["memberId"]
    uid, h = user_headers("820003")
    client = TestClient(app)
    url = api.url("/account/link")
    request_id = client.post(url, json={"memberId": member}, headers=h).json()["request"]["requestId"]
    api.ok(api.post(f"/admin/accounts/{request_id}/reject"))
    assert client.get(api.url("/account"), headers=h).json()["request"]["status"] == "REJECTED"
    request2 = client.post(url, json={"memberId": member}, headers=h).json()["request"]["requestId"]
    assert request2 != request_id
    assert client.delete(url, headers=h).json()["request"]["status"] == "CANCELLED"
    assert api.post(f"/admin/accounts/{request2}/approve").status_code == 409
    token = h["Cookie"].split("=", 1)[1]
    assert client.get(api.url("/admin/accounts"), headers={"Authorization": f"Bearer {token}"}).status_code == 401
    # 관리자 토큰을 사용자 쿠키에 넣어도 로그인되지 않는다.
    assert client.get("/api/auth/me", headers={"Cookie": f"{auth.USER_COOKIE}={api.token}"}).json()["user"] is None
    assert client.get("/api/auth/me", headers={"Cookie": f"{auth.USER_COOKIE}=malformed"}).json()["user"] is None
