"""관리자 초안 수정: 권한, 검증, 게시 상태와 공개 화면 반영."""
import pytest

from tests.test_article_writer import _preview


def test_edit_draft_then_publish(make_club):
    api = make_club("editdraft")
    article = _preview(api)
    path = f"/articles/{article['articleId']}"
    body = {"title": "  수정한 프리뷰  ", "summary": "수정 요약", "content": "첫 문단\n\n둘째 문단"}
    # 관전자에게는 수정 권한과 미게시 기사 조회 권한이 없다.
    assert api.patch(path, body, admin=False).status_code == 401
    assert api.get(path, admin=False).status_code == 404
    other = make_club("editother")
    assert other.patch(path, body).status_code == 404
    updated = api.ok(api.patch(path, body))
    assert updated["title"] == "수정한 프리뷰"
    assert updated["summary"] == body["summary"]
    assert updated["content"] == body["content"]
    assert updated["status"] == "GENERATED"
    assert updated["generationNo"] == article["generationNo"]
    assert updated["usedInsightIds"] == article["usedInsightIds"]
    api.ok(api.post(path + "/publish"))
    public = api.ok(api.get(path, admin=False))
    assert public["title"] == updated["title"] and public["content"] == body["content"]
    assert api.patch(path, body).status_code == 409
    # 게시했다 내린 기사도 게시 전 초안으로 취급하지 않는다.
    api.ok(api.post(path + "/reject"))
    assert api.patch(path, body).status_code == 409


def test_rejected_unpublished_draft_can_be_edited(make_club):
    api = make_club("editrejected")
    article = _preview(api)
    path = f"/articles/{article['articleId']}"
    api.ok(api.post(path + "/reject"))
    updated = api.ok(api.patch(path, {"title": "제목", "summary": "", "content": "본문"}))
    assert updated["summary"] == "" and updated["status"] == "REJECTED"


@pytest.mark.parametrize("field,value", [
    ("title", "   "), ("title", "가" * 201), ("title", None),
    ("summary", "가" * 501), ("content", "\n \n"), ("content", "가" * 16001),
], ids=["blank-title", "long-title", "null-title", "long-summary", "blank-body", "long-body"])
def test_invalid_article_edits_leave_draft_unchanged(make_club, field, value):
    api = make_club(f"editinvalid{field}{len(str(value))}")
    article = _preview(api)
    path = f"/articles/{article['articleId']}"
    body = {"title": "제목", "summary": "요약", "content": "본문", field: value}
    assert api.patch(path, body).status_code == 422
    assert api.ok(api.get(path))["title"] == article["title"]
