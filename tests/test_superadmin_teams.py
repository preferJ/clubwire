"""전체 관리자 운영팀 관리: 기존 기록 보존, 클럽별 소속과 인증 경계."""
from uuid import uuid4

import pytest
from sqlalchemy import func, select

from app.core.config import settings
from app.core.security import verify_password
from app.core.superadmin import superadmin_login_limiter
from app.models import AiArticle, Club, ClubAdmin, ClubSession, Member, SessionMember, SystemConfig, TitleType


def _slug(prefix="team"):
    return f"{prefix}-{uuid4().hex[:12]}"


def _ok(response, status=200):
    assert response.status_code == status, response.text
    return response.json()


@pytest.fixture
def super_headers(client, monkeypatch):
    monkeypatch.setattr(settings, "SUPER_ADMIN_PIN", "7418")
    superadmin_login_limiter.reset()
    result = _ok(client.post("/api/admin/auth", json={"password": "7418"}))
    yield {"Authorization": f"Bearer {result['accessToken']}"}
    superadmin_login_limiter.reset()


def _create_team(client, headers, *, slug=None, name="새 풋살팀", pin="8624", **extra):
    return _ok(client.post("/api/admin/clubs", headers=headers,
                           json={"clubSlug": slug or _slug(), "clubName": name, "adminPin": pin, **extra}), 201)


def _team_headers(client, slug, pin="8624"):
    result = _ok(client.post(f"/api/clubs/{slug}/admin/auth", json={"password": pin}))
    return {"Authorization": f"Bearer {result['accessToken']}"}


def _records(api, db):
    """기존 클럽의 선수·참석·일정·기사 fixture. 실제 운영 DB에는 접근하지 않는다."""
    cid = api.ok(api.get(""))["clubId"]
    members = [api.ok(api.post("/members", {"name": f"기존 선수{i}"}), 201)["memberId"] for i in range(2)]
    sid = api.ok(api.post("/sessions", {"sessionDate": "2026-12-20", "title": "보존할 일정"}), 201)["sessionId"]
    api.ok(api.post(f"/sessions/{sid}/members", {"memberIds": members}))
    article = AiArticle(club_id=cid, session_id=sid, article_type="PRE_MATCH", status="GENERATED",
                        model_name="template", prompt_version="test", generation_no=1,
                        title="보존할 기사", summary="기존 요약", content="기존 본문", request_json={"insights": []})
    db.add(article)
    db.commit()
    return {"clubId": cid, "memberIds": members, "sessionId": sid, "articleId": article.article_id}


@pytest.mark.parametrize("method", ["GET", "POST", "PATCH"])
def test_team_management_rejects_missing_and_club_admin_auth(client, make_club, method):
    api = make_club(_slug("local-admin"))
    cid = api.ok(api.get(""))["clubId"]
    path = f"/api/admin/clubs/{cid}" if method == "PATCH" else "/api/admin/clubs"
    body = {"clubSlug": _slug(), "clubName": "허용되지 않는 팀", "adminPin": "8624"}
    if method == "PATCH":
        body = {"clubName": "허용되지 않는 변경"}
    for headers in ({}, {"Authorization": f"Bearer {api.token}"}):
        response = client.request(method, path, headers=headers, **({"json": body} if method != "GET" else {}))
        assert response.status_code == 401
    assert api.ok(api.get(""))["clubName"] != "허용되지 않는 변경"


def test_global_list_includes_existing_ypr_data_and_accurate_counts(client, make_club, db, super_headers):
    ypr = make_club(_slug("ypr"))
    records = _records(ypr, db)
    club = db.get(Club, records["clubId"])
    club.club_name = "YPR"
    db.commit()
    other = _create_team(client, super_headers, name="다른 운영팀")

    rows = _ok(client.get("/api/admin/clubs", headers=super_headers))
    by_id = {row["clubId"]: row for row in rows}
    row = by_id[records["clubId"]]
    assert row == {"clubId": records["clubId"], "clubSlug": ypr.slug, "clubName": "YPR",
                   "sportType": "FUTSAL", "timezone": "Asia/Seoul", "active": True,
                   "memberCount": 2, "sessionCount": 1, "articleCount": 1}
    assert by_id[other["clubId"]]["memberCount"] == 0
    assert by_id[other["clubId"]]["sessionCount"] == 0
    assert by_id[other["clubId"]]["articleCount"] == 0
    # 전역 목록 조회가 기존 팀이나 기록을 새로 만들거나 바꾸지 않는다.
    assert db.get(Member, records["memberIds"][0]).club_id == records["clubId"]
    assert db.get(ClubSession, records["sessionId"]).club_id == records["clubId"]
    assert db.get(AiArticle, records["articleId"]).content == "기존 본문"


def test_creating_team_seeds_its_own_admin_config_and_titles(client, db, super_headers):
    created = _create_team(client, super_headers)
    cid = created["clubId"]
    assert created["sportType"] == "FUTSAL" and created["timezone"] == "Asia/Seoul" and created["active"] is True
    assert created["memberCount"] == created["sessionCount"] == created["articleCount"] == 0
    admins = list(db.scalars(select(ClubAdmin).where(ClubAdmin.club_id == cid)))
    assert len(admins) == 1 and admins[0].active_yn
    assert admins[0].password_hash != "8624" and verify_password(admins[0].password_hash, "8624")
    config = {row.config_key: row for row in db.scalars(select(SystemConfig).where(SystemConfig.club_id == cid))}
    assert "INITIAL_RATING" in config and "ARTICLE_PUBLISH_MODE" in config
    titles = {row.title_code: row for row in db.scalars(select(TitleType).where(TitleType.club_id == cid))}
    assert {"TOP_SCORER", "TOP_ASSIST", "MONTHLY_MVP"} <= titles.keys()
    assert all(row.club_id == cid for row in [*config.values(), *titles.values()])
    _team_headers(client, created["clubSlug"])


def test_two_created_teams_keep_member_and_session_ownership_separate(client, db, super_headers):
    a, b = [_create_team(client, super_headers) for _ in range(2)]
    records = []
    for team in (a, b):
        base = f"/api/clubs/{team['clubSlug']}"
        headers = _team_headers(client, team["clubSlug"])
        member = _ok(client.post(base + "/members", headers=headers, json={"name": "동명이인 선수"}), 201)
        session = _ok(client.post(base + "/sessions", headers=headers, json={"sessionDate": "2026-12-20"}), 201)
        _ok(client.post(base + f"/sessions/{session['sessionId']}/members", headers=headers,
                        json={"memberIds": [member["memberId"]]}))
        records.append((team, base, headers, member["memberId"], session["sessionId"]))
    assert records[0][3] != records[1][3] and records[0][4] != records[1][4]
    for i, (team, base, headers, mid, sid) in enumerate(records):
        assert db.get(Member, mid).club_id == team["clubId"]
        assert db.get(ClubSession, sid).club_id == team["clubId"]
        child = db.scalar(select(SessionMember).where(SessionMember.session_id == sid))
        assert child.member_id == mid  # SESSION_MEMBER -> SESSION -> CLUB 소유 경로
        assert [m["memberId"] for m in _ok(client.get(base + "/members"))] == [mid]
        foreign_mid = records[1 - i][3]
        assert client.post(base + f"/sessions/{sid}/members", headers=headers,
                           json={"memberIds": [foreign_mid]}).status_code == 404
        assert db.scalar(select(func.count()).select_from(SessionMember).where(SessionMember.session_id == sid)) == 1


def test_rename_preserves_ids_records_and_club_admin_access(client, make_club, db, super_headers):
    api = make_club(_slug("rename-old"))
    before = _records(api, db)
    new_slug = _slug("rename-new")
    changed = _ok(client.patch(f"/api/admin/clubs/{before['clubId']}", headers=super_headers,
                               json={"clubSlug": new_slug, "clubName": "이름을 바꾼 팀", "timezone": "UTC"}))
    assert changed["clubId"] == before["clubId"] and changed["clubSlug"] == new_slug
    assert changed["clubName"] == "이름을 바꾼 팀" and changed["timezone"] == "UTC"
    assert (changed["memberCount"], changed["sessionCount"], changed["articleCount"]) == (2, 1, 1)
    assert client.get(f"/api/clubs/{api.slug}").status_code == 404
    headers = {"Authorization": f"Bearer {api.token}"}
    base = f"/api/clubs/{new_slug}"
    assert _ok(client.get(base + "/admin/me", headers=headers))["clubId"] == before["clubId"]
    assert {m["memberId"] for m in _ok(client.get(base + "/members"))} == set(before["memberIds"])
    assert _ok(client.get(base + f"/sessions/{before['sessionId']}"))["sessionId"] == before["sessionId"]
    article = _ok(client.get(base + f"/articles/{before['articleId']}", headers=headers))
    assert article["content"] == "기존 본문"
    assert db.get(AiArticle, before["articleId"]).club_id == before["clubId"]


def test_pin_reset_updates_only_target_team(client, db, super_headers):
    a, b = [_create_team(client, super_headers) for _ in range(2)]
    other_hash = db.scalar(select(ClubAdmin.password_hash).where(ClubAdmin.club_id == b["clubId"]))
    _ok(client.patch(f"/api/admin/clubs/{a['clubId']}", headers=super_headers, json={"adminPin": "5362"}))
    assert client.post(f"/api/clubs/{a['clubSlug']}/admin/auth", json={"password": "8624"}).status_code == 401
    _team_headers(client, a["clubSlug"], "5362")
    _team_headers(client, b["clubSlug"], "8624")
    assert db.scalar(select(ClubAdmin.password_hash).where(ClubAdmin.club_id == b["clubId"])) == other_hash
    assert client.post(f"/api/clubs/{b['clubSlug']}/admin/auth", json={"password": "5362"}).status_code == 401


def test_invalid_timezone_cannot_create_or_partially_update_team(client, db, super_headers):
    invalid_slug = _slug("bad-zone")
    before_count = db.scalar(select(func.count()).select_from(Club))
    response = client.post("/api/admin/clubs", headers=super_headers,
                           json={"clubSlug": invalid_slug, "clubName": "저장되면 안 되는 팀",
                                 "adminPin": "8624", "timezone": "Invalid/Time_Zone"})
    assert response.status_code == 400 and response.json()["error"]["code"] == "INVALID_TIMEZONE"
    assert db.scalar(select(func.count()).select_from(Club)) == before_count
    assert db.scalar(select(Club).where(Club.club_slug == invalid_slug)) is None
    db.rollback()  # 다른 API 세션에서 만드는 다음 팀을 새 DB 스냅샷으로 조회한다.

    created = _create_team(client, super_headers)
    changed_slug = _slug("not-saved")
    response = client.patch(f"/api/admin/clubs/{created['clubId']}", headers=super_headers,
                            json={"clubSlug": changed_slug, "clubName": "저장되면 안 되는 이름",
                                  "adminPin": "5362", "timezone": "Invalid/Time_Zone"})
    assert response.status_code == 400
    db.rollback()
    club = db.get(Club, created["clubId"])
    assert (club.club_slug, club.club_name, club.timezone) == (created["clubSlug"], created["clubName"], created["timezone"])
    _team_headers(client, created["clubSlug"], "8624")
    assert client.get(f"/api/clubs/{changed_slug}").status_code == 404


def test_duplicate_slug_is_safe_on_creation_and_atomic_update(client, db, super_headers):
    a, b = [_create_team(client, super_headers) for _ in range(2)]
    before_count = db.scalar(select(func.count()).select_from(Club))
    response = client.post("/api/admin/clubs", headers=super_headers,
                           json={"clubSlug": a["clubSlug"], "clubName": "중복 팀", "adminPin": "5362"})
    assert response.status_code == 409
    assert db.scalar(select(func.count()).select_from(Club)) == before_count
    response = client.patch(f"/api/admin/clubs/{b['clubId']}", headers=super_headers,
                            json={"clubSlug": a["clubSlug"], "clubName": "덮어쓰면 안 되는 이름", "adminPin": "5362"})
    assert response.status_code == 409
    db.expire_all()
    assert db.get(Club, b["clubId"]).club_slug == b["clubSlug"]
    assert db.get(Club, b["clubId"]).club_name == b["clubName"]
    _team_headers(client, a["clubSlug"])
    _team_headers(client, b["clubSlug"])


@pytest.mark.parametrize("body", [{}, {"clubName": None}, {"clubSlug": None}, {"timezone": None}, {"adminPin": None}])
def test_empty_or_null_updates_are_rejected(client, super_headers, body):
    created = _create_team(client, super_headers)
    response = client.patch(f"/api/admin/clubs/{created['clubId']}", headers=super_headers, json=body)
    assert response.status_code == 400


@pytest.mark.parametrize("slug", ["InvalidSlug", "bad/slug", "contains space", ""])
def test_invalid_slugs_are_rejected(client, super_headers, slug):
    response = client.post("/api/admin/clubs", headers=super_headers,
                           json={"clubSlug": slug, "clubName": "검증 대상 팀", "adminPin": "8624"})
    assert response.status_code == 422


def test_removing_team_closes_only_its_websocket_and_restore_reopens(client, make_club, super_headers):
    from starlette.websockets import WebSocketDisconnect

    a = make_club(_slug("ws-a"))
    b = make_club(_slug("ws-b"))
    cid = a.ok(a.get(""))["clubId"]
    with client.websocket_connect(f"/ws/clubs/{a.slug}") as ws_a, \
            client.websocket_connect(f"/ws/clubs/{b.slug}") as ws_b:
        assert ws_a.receive_json()["type"] == "HELLO"
        assert ws_b.receive_json()["type"] == "HELLO"
        _ok(client.delete(f"/api/admin/clubs/{cid}", headers=super_headers))
        closed = ws_a.receive()
        assert closed["type"] == "websocket.close" and closed["code"] == 4404
        ws_b.send_text("ping")
        assert ws_b.receive_json()["type"] == "PONG"

    with pytest.raises(WebSocketDisconnect) as exc:
        with client.websocket_connect(f"/ws/clubs/{a.slug}"):
            pass
    assert exc.value.code == 4404
    _ok(client.post(f"/api/admin/clubs/{cid}/restore", headers=super_headers))
    with client.websocket_connect(f"/ws/clubs/{a.slug}") as restored:
        assert restored.receive_json()["clubId"] == cid
        restored.send_text("ping")
        assert restored.receive_json()["type"] == "PONG"


@pytest.mark.parametrize("method,suffix", [("DELETE", ""), ("POST", "/restore")])
def test_deactivate_and_restore_require_global_admin(client, make_club, method, suffix):
    api = make_club(_slug("protected-status"))
    cid = api.ok(api.get(""))["clubId"]
    path = f"/api/admin/clubs/{cid}{suffix}"
    for headers in ({}, {"Authorization": f"Bearer {api.token}"}):
        assert client.request(method, path, headers=headers).status_code == 401
    assert api.ok(api.get(""))["clubId"] == cid


def test_deactivation_and_restore_preserve_records_and_block_inactive_team_routes(
        client, make_club, db, super_headers):
    api = make_club(_slug("status-records"))
    other = make_club(_slug("unaffected-team"))
    records = _records(api, db)
    cid, sid, aid = records["clubId"], records["sessionId"], records["articleId"]
    other_cid = other.ok(other.get(""))["clubId"]
    api.ok(api.post(f"/articles/{aid}/publish"))
    assert api.get(f"/articles/{aid}", admin=False).status_code == 200
    old_admin_hash = db.scalar(select(ClubAdmin.password_hash).where(ClubAdmin.club_id == cid))
    db.rollback()

    path = f"/api/admin/clubs/{cid}"
    inactive = _ok(client.delete(path, headers=super_headers))
    assert inactive["clubId"] == cid and inactive["active"] is False
    assert (inactive["memberCount"], inactive["sessionCount"], inactive["articleCount"]) == (2, 1, 1)
    listed = {row["clubId"]: row for row in _ok(client.get("/api/admin/clubs", headers=super_headers))}
    assert listed[cid] == inactive and listed[other_cid]["active"] is True

    # 주소를 아는 공개 사용자와 삭제 이전 관리자 토큰 모두 비활성 팀에 접근할 수 없다.
    for endpoint in ("", "/members", "/sessions", f"/sessions/{sid}", "/articles", f"/articles/{aid}"):
        assert api.get(endpoint, admin=False).status_code == 404
        assert api.get(endpoint).status_code == 404
    assert api.post("/admin/auth", {"password": "7777"}, admin=False).status_code == 404
    assert api.post("/members", {"name": "생성되면 안 되는 선수"}).status_code == 404
    assert api.post("/sessions", {"sessionDate": "2026-12-21"}).status_code == 404
    assert api.post(f"/sessions/{sid}/members", {"memberIds": records["memberIds"]}).status_code == 404
    assert api.patch(f"/articles/{aid}", {"title": "변경 불가", "summary": "변경 불가", "content": "변경 불가"}).status_code == 404

    assert other.ok(other.get(""))["clubId"] == other_cid
    assert other.get("/members").status_code == 200
    assert other.get("/admin/me").status_code == 200
    assert other.post("/admin/auth", {"password": "7777"}, admin=False).status_code == 200

    # 두 번 눌러도 물리 삭제하거나 원래 FK 관계를 바꾸지 않는다.
    assert _ok(client.delete(path, headers=super_headers)) == inactive
    db.rollback()
    assert db.get(Club, cid).active_yn is False
    assert {m.member_id for m in db.scalars(select(Member).where(Member.club_id == cid))} == set(records["memberIds"])
    session = db.get(ClubSession, sid)
    assert session.club_id == cid and session.deleted_at is None
    attendees = list(db.scalars(select(SessionMember).where(SessionMember.session_id == sid)))
    assert {row.member_id for row in attendees} == set(records["memberIds"])
    article = db.get(AiArticle, aid)
    assert article.club_id == cid and article.session_id == sid
    assert article.title == "보존할 기사" and article.content == "기존 본문" and article.published_yn is True
    assert db.scalar(select(ClubAdmin.password_hash).where(ClubAdmin.club_id == cid)) == old_admin_hash
    db.rollback()

    restored = _ok(client.post(path + "/restore", headers=super_headers))
    assert restored == {**inactive, "active": True}
    assert _ok(client.post(path + "/restore", headers=super_headers)) == restored
    _team_headers(client, api.slug, "7777")
    assert api.ok(api.get(""))["clubId"] == cid
    assert {m["memberId"] for m in api.ok(api.get("/members"))} == set(records["memberIds"])
    assert api.ok(api.get(f"/sessions/{sid}"))["sessionId"] == sid
    assert api.ok(api.get(f"/articles/{aid}", admin=False))["content"] == "기존 본문"
    rows = _ok(client.get("/api/admin/clubs", headers=super_headers))
    assert [row["clubId"] for row in rows].count(cid) == 1
    assert next(row for row in rows if row["clubId"] == cid) == restored


@pytest.mark.parametrize("method,suffix", [("DELETE", ""), ("POST", "/restore")])
def test_deactivate_and_restore_unknown_team_return_not_found(client, db, super_headers, method, suffix):
    cid = (db.scalar(select(func.max(Club.club_id))) or 0) + 1000000
    response = client.request(method, f"/api/admin/clubs/{cid}{suffix}", headers=super_headers)
    assert response.status_code == 404 and response.json()["error"]["code"] == "CLUB_NOT_FOUND"
