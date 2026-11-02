"""메인 팀 마크 크기(관리자 슬라이더) · 상단 공지 크기(3단계) · 선수 삭제(목록에서만 숨김, 복원)."""
import json

from sqlalchemy import select

from app.core.database import SessionLocal
from app.core.timeutil import local_today
from app.models import Member


def _closed_session(api, member_ids, d):
    """일정 하나: 참석 → 2팀 확정 → 한 경기(A팀 골) 확정 → 마감."""
    sid = api.ok(api.post("/sessions", {"sessionDate": d.isoformat()}), 201)["sessionId"]
    api.ok(api.post(f"/sessions/{sid}/members", {"memberIds": member_ids}))
    gen = api.ok(api.post(f"/sessions/{sid}/teams/generate", {"teamCount": 2}))
    api.ok(api.post(f"/sessions/{sid}/teams/confirm", {"generationId": gen["generationId"]}))
    m = api.next_match(sid)
    mid = m["matchId"]
    api.ok(api.post(f"/matches/{mid}/start"))
    scorer = api.ok(api.get(f"/matches/{mid}"))["teamA"]["members"][0]["memberId"]
    api.ok(api.post(f"/matches/{mid}/goals", {"teamId": m["teamA"]["sessionTeamId"], "scorerMemberId": scorer}))
    api.ok(api.post(f"/matches/{mid}/end"))
    api.ok(api.post(f"/matches/{mid}/finalize"))
    api.ok(api.post(f"/sessions/{sid}/close"))
    return sid


def test_crest_size_is_saved_by_admin_and_validated(make_club):
    api = make_club("crestsize")
    assert api.ok(api.get("/appearance", admin=False))["crestSize"] == 44  # 저장 전 = 지금까지 크기
    saved = api.ok(api.patch("/admin/appearance", {"crestSize": 60}))
    assert saved["crestSize"] == 60 and saved["crest"]["mode"] == "auto"  # 크기만 바꾸면 마크 설정은 그대로
    assert api.ok(api.get("", admin=False))["appearance"]["crestSize"] == 60  # 탭 머리(ClubBar)가 읽는 값
    for bad in (31, 73, 50.5, "60"):
        assert api.patch("/admin/appearance", {"crestSize": bad}).status_code == 422
    assert api.patch("/admin/appearance", {"crestSize": None}).status_code == 400
    assert api.patch("/admin/appearance", {"crestSize": 40}, admin=False).status_code == 401
    same = api.ok(api.patch("/admin/appearance", {"crestSize": 60}))
    assert same["updatedAt"] == saved["updatedAt"]  # 같은 값이면 변경 없음(알림도 없음)


def test_announcement_size_has_three_steps(make_club):
    api = make_club("noticesize")
    api.ok(api.patch("/admin/content", {"announcement": "토요일 8시 시작"}))
    before = api.ok(api.get("/content", admin=False))
    assert before["announcementSize"] == "medium"
    large = api.ok(api.patch("/admin/content", {"announcementSize": "large"}))
    assert large["announcementSize"] == "large" and large["announcement"] == "토요일 8시 시작"
    assert large["announcementUpdatedAt"] == before["announcementUpdatedAt"]  # 크기만 바꾸면 공지 수정 시각 그대로
    assert api.ok(api.get("/content", admin=False))["announcementSize"] == "large"
    assert api.patch("/admin/content", {"announcementSize": "huge"}).status_code == 422
    assert api.ok(api.patch("/admin/content", {"announcementSize": None}))["announcementSize"] == "medium"
    assert api.ok(api.patch("/admin/content", {"announcementSize": "small"}))["announcementSize"] == "small"


def test_deleted_member_is_hidden_from_lists_but_records_stay(make_club):
    api = make_club("mdelete")
    ids = [api.ok(api.post("/members", {"name": f"선수{i}"}), 201)["memberId"] for i in range(6)]
    api.ok(api.patch("/admin/config", {"values": {"MONTHLY_MVP_MIN_SESSIONS": 1}}))
    sid = _closed_session(api, ids, local_today("Asia/Seoul"))

    race = api.ok(api.get("/stats/mvp-race", admin=False))["candidates"]
    assert race, "이긴 팀 선수는 이달의 MVP 후보"
    x = race[0]["memberId"]
    x_name = next(m["name"] for m in api.ok(api.get("/members")) if m["memberId"] == x)
    before_summary = api.ok(api.get("/summary", admin=False))["activeMembers"]
    before_detail = api.ok(api.get(f"/stats/members/{x}", admin=False))["summary"]

    gone = api.ok(api.delete(f"/members/{x}"))
    assert gone["deleted"] is True and gone["deletedAt"]
    assert api.ok(api.delete(f"/members/{x}"))["deletedAt"] == gone["deletedAt"]  # 다시 눌러도 그대로

    # 목록에서 숨김: 선수단(공개) · 관리자 목록 · 기록 순위 · MVP 후보 · 요약 수
    assert x not in [m["memberId"] for m in api.ok(api.get("/members", admin=False))]
    assert x not in [m["memberId"] for m in api.ok(api.get("/members", params={"includeInactive": "true"}))]
    assert x not in [m["memberId"] for m in api.ok(api.get("/stats/members", admin=False))]
    assert x not in [c["memberId"] for c in api.ok(api.get("/stats/mvp-race", admin=False))["candidates"]]
    assert api.ok(api.get("/summary", admin=False))["activeMembers"] == before_summary - 1
    # 삭제한 선수 목록은 관리자만
    assert [m["memberId"] for m in api.ok(api.get("/members", params={"deleted": "true"}))] == [x]
    assert api.get("/members", params={"deleted": "true"}, admin=False).status_code == 401

    # 지난 기록은 그대로: 선수 상세(링크) · 지난 일정 명단 · DB 행
    detail = api.ok(api.get(f"/stats/members/{x}", admin=False))["summary"]
    assert detail["deleted"] is True and detail["games"] == before_detail["games"] == 1
    assert x_name in json.dumps(api.ok(api.get(f"/sessions/{sid}", admin=False)), ensure_ascii=False)
    with SessionLocal() as s:
        assert s.scalar(select(Member).where(Member.member_id == x)).deleted_at is not None

    # 새 참석 · 수정 · 새 수상은 막힘
    sid2 = api.ok(api.post("/sessions", {"sessionDate": "2027-03-06"}), 201)["sessionId"]
    r = api.post(f"/sessions/{sid2}/members", {"memberIds": [x]})
    assert r.status_code == 404 and r.json()["error"]["code"] == "MEMBER_NOT_FOUND"
    r = api.patch(f"/members/{x}", {"name": "바꾸면 안 됨"})
    assert r.status_code == 409 and r.json()["error"]["code"] == "MEMBER_DELETED"

    # 복원: 목록 · 순위로 돌아오고 수정 가능
    back = api.ok(api.post(f"/members/{x}/restore"))
    assert back["deleted"] is False and back["deletedAt"] is None
    assert x in [m["memberId"] for m in api.ok(api.get("/stats/members", admin=False))]
    assert api.ok(api.get("/members", params={"deleted": "true"})) == []
    api.ok(api.patch(f"/members/{x}", {"jerseyNumber": 7}))


def test_member_in_unfinished_session_cannot_be_deleted(make_club):
    api = make_club("mdelopen")
    ids = [api.ok(api.post("/members", {"name": f"참석{i}"}), 201)["memberId"] for i in range(4)]
    sid = api.ok(api.post("/sessions", {"sessionDate": "2027-03-13"}), 201)["sessionId"]
    api.ok(api.post(f"/sessions/{sid}/members", {"memberIds": ids}))
    r = api.delete(f"/members/{ids[0]}")
    assert r.status_code == 409 and r.json()["error"]["code"] == "MEMBER_IN_OPEN_SESSION" and "3/13" in r.json()["error"]["message"]
    assert api.ok(api.delete(f"/sessions/{sid}/members/{ids[0]}"))  # 참석 취소 후에는 삭제 가능
    assert api.ok(api.delete(f"/members/{ids[0]}"))["deleted"] is True
    # 삭제한 선수는 관리자 지각 추가(팀 배정)에서도 찾을 수 없음
    assert ids[0] not in [m["memberId"] for m in api.ok(api.get("/members"))]
