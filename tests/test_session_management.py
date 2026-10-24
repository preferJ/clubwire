"""프리뷰 수동 검토, 일정 삭제 보관함과 권한/기록 보존."""
from tests.test_article_writer import _preview
from tests.test_e2e_scenario import _play


def test_preview_never_auto_publishes(make_club):
    api = make_club("previewreview")
    api.ok(api.patch("/admin/config", {"values": {"ARTICLE_PUBLISH_MODE": "AUTO"}}))
    article = _preview(api)
    assert article["status"] == "GENERATED"
    assert api.ok(api.get("/articles", admin=False)) == []
    path = f"/articles/{article['articleId']}"
    api.ok(api.post(path + "/reject"))
    api.ok(api.patch(path, {"title": "검토 완료", "summary": "", "content": "검토한 내용"}))
    api.ok(api.post(path + "/publish"))
    assert api.ok(api.get(path, admin=False))["title"] == "검토 완료"


def test_delete_session_permissions_and_archive(make_club):
    api = make_club("sessionarchive")
    article = _preview(api)
    sid = article["sessionId"]
    path = f"/sessions/{sid}"
    api.ok(api.post(f"/articles/{article['articleId']}/publish"))
    assert api.c.delete(api.url(path)).status_code == 401
    other = make_club("sessionother")
    assert other.delete(path).status_code == 404
    deleted = api.ok(api.delete(path))
    assert deleted["deletedAt"] and deleted["status"] == "CANCELLED"
    assert api.ok(api.delete(path))["deletedAt"] == deleted["deletedAt"]
    assert api.ok(api.get("/sessions", admin=False)) == []
    assert api.ok(api.get("/sessions", params={"category": "upcoming"})) == []
    assert api.ok(api.get("/sessions", params={"category": "completed"})) == []
    archived = api.ok(api.get("/sessions", params={"category": "deleted"}))
    assert [s["sessionId"] for s in archived] == [sid]
    assert api.get("/sessions", params={"category": "deleted"}, admin=False).status_code == 401
    assert api.get(path, admin=False).status_code == 404
    assert api.ok(api.get(path))["deletedAt"]
    assert api.patch(path, {"title": "수정 차단"}).status_code == 404
    assert api.post(path + "/teams/generate", {"teamCount": 2}).status_code == 404
    assert api.post(path + "/close").status_code == 404
    assert api.ok(api.get("/articles", admin=False)) == []
    assert api.get(f"/articles/{article['articleId']}", admin=False).status_code == 404
    assert api.post(f"/articles/{article['articleId']}/publish").status_code == 404
    assert api.ok(api.get("/summary"))["sessions"] == 0


def test_complete_before_deleting_preserves_match_and_stats(make_club):
    api = make_club("archivecomplete")
    article = _preview(api)
    sid = article["sessionId"]
    match = api.next_match(sid)
    mid = match["matchId"]
    api.ok(api.post(f"/matches/{mid}/start"))
    assert api.delete(f"/sessions/{sid}").status_code == 409
    assert api.ok(api.get("/sessions", params={"category": "upcoming"}))[0]["sessionId"] == sid
    api.ok(api.post(f"/matches/{mid}/end"))
    api.ok(api.post(f"/matches/{mid}/finalize"))
    _play(api, sid, 2, 1)
    api.ok(api.post(f"/sessions/{sid}/close"))
    before = api.ok(api.get("/stats/members"))
    assert any(m["goals"] > 0 for m in before)
    assert api.ok(api.get("/sessions", params={"category": "completed"}))[0]["sessionId"] == sid
    deleted = api.ok(api.delete(f"/sessions/{sid}"))
    assert deleted["status"] == "CLOSED" and deleted["deletedAt"]
    assert api.ok(api.get("/sessions", params={"category": "completed"})) == []
    assert api.ok(api.get("/stats/members")) == before
    assert api.ok(api.get(f"/sessions/{sid}"))["matches"]
    assert api.post(f"/matches/{mid}/unfinalize").status_code == 409


def test_category_filter_applies_before_limit(make_club):
    api = make_club("archivefilter")
    old = api.ok(api.post("/sessions", {"sessionDate": "2026-11-01"}), 201)["sessionId"]
    api.ok(api.delete(f"/sessions/{old}"))
    api.ok(api.post("/sessions", {"sessionDate": "2026-12-01"}), 201)
    result = api.ok(api.get("/sessions", params={"category": "deleted", "limit": 1}))
    assert [s["sessionId"] for s in result] == [old]
    assert api.get("/sessions", params={"category": "unknown"}).status_code == 422
