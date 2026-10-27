"""공개 운영수칙/상단 공지의 관리자 편집, 클럽 격리 및 실시간 반영."""
import pytest

from app.core.ws import hub
from tests.conftest import Api


def test_content_partial_update_clear_and_public_persistence(make_club, monkeypatch):
    api = make_club("content-edit")
    assert api.ok(api.get("/content", admin=False)) == {
        "operatingRules": None, "operatingRulesUpdatedAt": None,
        "announcement": "", "announcementUpdatedAt": None,
    }
    emitted = []
    monkeypatch.setattr(hub, "publish", lambda channel, message: emitted.append((channel, message)))

    rules = "## YPR 운영수칙\n\n- 경기 10분 전 도착\n- 서로 존중하기"
    first = api.ok(api.patch("/admin/content", {"operatingRules": rules, "announcement": "  이번 주\n  오후 3시   집합!  "}))
    assert first["operatingRules"] == rules and first["announcement"] == "이번 주 오후 3시 집합!"
    assert first["operatingRulesUpdatedAt"].endswith("Z") and first["announcementUpdatedAt"].endswith("Z")
    assert emitted[-1][1] == {"type": "CLUB_CONTENT_UPDATED"}
    assert len(emitted) == 1
    assert api.ok(api.get("/content", admin=False)) == first

    # 다른 항목만 수정하면 운영수칙과 수정 시각은 유지한다.
    edited = api.ok(api.patch("/admin/content", {"announcement": "새 공지"}))
    assert edited["operatingRules"] == first["operatingRules"]
    assert edited["operatingRulesUpdatedAt"] == first["operatingRulesUpdatedAt"]
    count = len(emitted)
    assert api.ok(api.patch("/admin/content", {"announcement": " 새 공지 "})) == edited
    assert api.ok(api.patch("/admin/content", {})) == edited
    assert len(emitted) == count

    assert api.ok(api.patch("/admin/content", {"announcement": "  \n "}))["announcement"] == ""
    assert api.ok(api.patch("/admin/content", {"operatingRules": ""}))["operatingRules"] == ""
    restored = api.ok(api.patch("/admin/content", {"operatingRules": None, "announcement": None}))
    assert restored["operatingRules"] is None and restored["announcement"] == ""
    assert api.ok(api.get("/content", admin=False)) == restored


def test_content_writes_require_the_correct_club_admin(make_club):
    first = make_club("content-auth-first")
    second = make_club("content-auth-second")
    payload = {"announcement": "첫 클럽 공지", "operatingRules": "첫 클럽 수칙"}
    assert first.patch("/admin/content", payload, admin=False).status_code == 401
    wrong = Api(first.c, first.slug)
    wrong.token = second.token
    assert wrong.patch("/admin/content", payload).status_code == 403
    saved = first.ok(first.patch("/admin/content", payload))
    assert first.ok(first.get("/content", admin=False)) == saved
    assert second.ok(second.get("/content", admin=False))["announcement"] == ""
    assert second.ok(second.get("/content", admin=False))["operatingRules"] is None


@pytest.mark.parametrize("payload", [
    {"announcement": "가" * 501, "operatingRules": "이것도 저장되면 안 됨"},
    {"operatingRules": "가" * 20001, "announcement": "이것도 저장되면 안 됨"},
    {"announcement": False}, {"operatingRules": 42}, {"unsupported": "값"},
])
def test_invalid_content_does_not_save_any_fields(make_club, payload, request):
    api = make_club(f"content-invalid-{request.node.callspec.indices['payload']}")
    original = api.ok(api.patch("/admin/content", {"announcement": "기존 공지", "operatingRules": "기존 수칙"}))
    assert api.patch("/admin/content", payload).status_code == 422
    assert api.ok(api.get("/content", admin=False)) == original


def test_content_accepts_maximum_multibyte_text_and_announces_commit(make_club):
    api = make_club("content-multibyte")
    rules = "🏆" * 20000
    with api.c.websocket_connect(f"/ws/clubs/{api.slug}") as ws:
        assert ws.receive_json()["type"] == "HELLO"
        saved = api.ok(api.patch("/admin/content", {"operatingRules": rules, "announcement": "공" * 500}))
        assert ws.receive_json() == {"type": "CLUB_CONTENT_UPDATED"}
    assert saved["operatingRules"] == rules
    assert api.ok(api.get("/content", admin=False)) == saved
