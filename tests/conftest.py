import os

os.environ.setdefault("DATABASE_URL", "mysql+pymysql://clubwire:clubwire@localhost:3306/clubwire_test?charset=utf8mb4")
os.environ["ARTICLE_GENERATION_SYNC"] = "true"
os.environ["AI_PROVIDER"] = "stub"
os.environ["ENABLE_BACKGROUND_JOBS"] = "false"

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.core.database import SessionLocal, engine  # noqa: E402
from app.core.security import login_limiter  # noqa: E402
from app.main import app  # noqa: E402
from app.models import Base  # noqa: E402
from app.services import club_service  # noqa: E402


@pytest.fixture(scope="session", autouse=True)
def schema():
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    yield


@pytest.fixture(scope="session")
def client():
    with TestClient(app) as c:
        yield c


@pytest.fixture
def db():
    with SessionLocal() as s:
        yield s


class Api:
    """테스트용 얇은 클라이언트: /api/clubs/{slug} 접두사 + 관리자 토큰."""

    def __init__(self, client: TestClient, slug: str):
        self.c = client
        self.slug = slug
        self.token: str | None = None

    def url(self, path: str) -> str:
        return f"/api/clubs/{self.slug}{path}"

    def _h(self, admin: bool):
        return {"Authorization": f"Bearer {self.token}"} if admin and self.token else {}

    def get(self, path, admin=True, **kw):
        return self.c.get(self.url(path), headers=self._h(admin), **kw)

    def post(self, path, json=None, admin=True, **kw):
        return self.c.post(self.url(path), json=json, headers=self._h(admin), **kw)

    def patch(self, path, json=None, admin=True):
        return self.c.patch(self.url(path), json=json, headers=self._h(admin))

    def delete(self, path, admin=True):
        return self.c.delete(self.url(path), headers=self._h(admin))

    def ok(self, resp, status=200):
        assert resp.status_code == status, resp.text
        return resp.json()

    def next_match(self, sid, teams=None):
        """다음 경기 생성. teams=None이면 추천 대진(가장 오래 쉰 두 팀)을 그대로 사용."""
        if teams is None:
            sug = self.ok(self.get(f"/sessions/{sid}/matches/next-suggestion"))
            teams = (sug["suggestedTeamAId"], sug["suggestedTeamBId"])
        return self.ok(self.post(f"/sessions/{sid}/matches/next", {"teamAId": teams[0], "teamBId": teams[1]}), 201)

    def login(self, pin="7777"):
        r = self.post("/admin/auth", {"password": pin}, admin=False)
        self.token = self.ok(r)["accessToken"]
        return self


@pytest.fixture
def make_club(client):
    def _make(slug: str, pin: str = "7777") -> Api:
        login_limiter.reset()
        with SessionLocal() as s:
            club_service.create_club(s, slug, f"{slug} FC", pin)
        return Api(client, slug).login(pin)
    return _make
