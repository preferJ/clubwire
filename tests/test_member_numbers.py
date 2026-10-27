"""등번호는 관리자만 변경하며 공개 선수단/프로필에 동일하게 표시한다."""
import pytest

from app.models import Member, PlayerRating
from tests.conftest import Api


def test_jersey_number_create_update_clear_and_public_views(make_club, db):
    api = make_club("jersey-profile")
    member = api.ok(api.post("/members", {
        "name": "등번호 선수", "jerseyNumber": 0, "initialRating": 1048,
        "joinedAt": "2021-03-14", "birthYear": 1992,
    }), 201)
    mid = member["memberId"]
    assert member["jerseyNumber"] == 0
    before_rating = db.get(PlayerRating, mid).current_rating

    def public_number(expected):
        assert next(m for m in api.ok(api.get("/members", admin=False)) if m["memberId"] == mid)["jerseyNumber"] == expected
        assert next(m for m in api.ok(api.get("/stats/members", admin=False)) if m["memberId"] == mid)["jerseyNumber"] == expected
        detail = api.ok(api.get(f"/stats/members/{mid}", admin=False))
        assert detail["summary"]["jerseyNumber"] == detail["profile"]["jerseyNumber"] == expected

    public_number(0)
    edited = api.ok(api.patch(f"/members/{mid}", {"jerseyNumber": 99}))
    assert edited["jerseyNumber"] == 99
    public_number(99)

    # 다른 정보만 수정한 경우 등번호를 그대로 둔다.
    renamed = api.ok(api.patch(f"/members/{mid}", {"name": "새 선수 이름"}))
    assert renamed["jerseyNumber"] == 99
    assert renamed["joinedAt"] == "2021-03-14" and renamed["birthYear"] == 1992
    db.rollback()  # API가 커밋한 뒤 새 DB snapshot으로 원본 레이팅 보존을 확인한다.
    assert db.get(Member, mid).initial_rating == 1048
    assert db.get(PlayerRating, mid).current_rating == before_rating

    assert api.ok(api.patch(f"/members/{mid}", {"jerseyNumber": None}))["jerseyNumber"] is None
    public_number(None)
    # 미입력 신규 선수도 기본값은 미지정이며 중복 등번호 입력을 금지하지 않는다.
    assert api.ok(api.post("/members", {"name": "미지정 선수"}), 201)["jerseyNumber"] is None
    api.ok(api.patch(f"/members/{mid}", {"jerseyNumber": 0}))
    assert api.ok(api.post("/members", {"name": "다른 0번 선수", "jerseyNumber": 0}), 201)["jerseyNumber"] == 0


@pytest.mark.parametrize("number", [-1, 100, 1.5, True, False, "7", ""])
def test_jersey_number_rejects_invalid_create_and_update(make_club, number, request):
    api = make_club(f"jersey-invalid-{request.node.callspec.indices['number']}")
    member = api.ok(api.post("/members", {"name": "유효한 선수", "jerseyNumber": 7}), 201)
    assert api.post("/members", {"name": "잘못된 번호", "jerseyNumber": number}).status_code == 422
    assert api.patch(f"/members/{member['memberId']}", {"jerseyNumber": number}).status_code == 422
    members = api.ok(api.get("/members", admin=False))
    assert len(members) == 1 and members[0]["jerseyNumber"] == 7


def test_jersey_number_is_admin_only_and_club_scoped(make_club):
    first = make_club("jersey-auth-first")
    second = make_club("jersey-auth-second")
    member = first.ok(first.post("/members", {"name": "첫 클럽 선수", "jerseyNumber": 11}), 201)
    mid = member["memberId"]

    assert first.post("/members", {"name": "무권한 선수", "jerseyNumber": 1}, admin=False).status_code == 401
    assert first.patch(f"/members/{mid}", {"jerseyNumber": 12}, admin=False).status_code == 401
    assert second.patch(f"/members/{mid}", {"jerseyNumber": 12}).status_code == 404
    assert second.get(f"/stats/members/{mid}", admin=False).status_code == 404

    wrong_club_token = Api(first.c, first.slug)
    wrong_club_token.token = second.token
    assert wrong_club_token.patch(f"/members/{mid}", {"jerseyNumber": 13}).status_code == 403
    assert first.ok(first.get("/members", admin=False))[0]["jerseyNumber"] == 11
