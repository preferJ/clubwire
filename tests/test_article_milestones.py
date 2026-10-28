"""기사 이정표: 본문과 독립된 전체 표·당시 스냅샷·기존 응답 호환."""
from copy import deepcopy

import pytest
from sqlalchemy import delete, select

from app.models import AiArticle, AiArticleInsight, Club, ClubSession, Insight
from app.wire.article_service import create_article, run_generation
from tests.test_article_writer import _preview


def _milestone(insight_id, member_id, name, metric="goals", milestone=10, remaining=1):
    return {"id": insight_id, "type": "MILESTONE_EXPECTED", "category": "MILESTONE", "importance": 48,
            "subject": {"memberId": member_id, "name": name},
            "facts": {"member": {"memberId": member_id, "name": name}, "metric": metric,
                      "milestone": milestone, "current": milestone - remaining, "remaining": remaining}}


def test_public_article_exposes_all_milestone_snapshots(make_club, db):
    api = make_club("milestonespublic")
    article = _preview(api)
    aid, sid = article["articleId"], article["sessionId"]
    members = api.ok(api.get("/members"))
    used_id = db.scalar(select(Insight.insight_id).where(Insight.session_id == sid))
    assert used_id is not None
    used = _milestone(used_id, members[0]["memberId"], "본문 선수")
    first = _milestone(used_id + 100000, members[1]["memberId"], "김응철", "assists")
    second = _milestone(used_id + 100001, members[2]["memberId"], "유창우", "games", 50)
    third = _milestone(used_id + 100002, members[3]["memberId"], "윤영문", "goals", 10, 2)
    unrelated = {**_milestone(used_id + 100003, members[4]["memberId"], "다른 기록"), "type": "SCORING_STREAK"}
    a = db.get(AiArticle, aid)
    a.request_json = {"insights": [used, first, unrelated, second, third]}
    db.execute(delete(AiArticleInsight).where(AiArticleInsight.article_id == aid))
    db.add(AiArticleInsight(article_id=aid, insight_id=used_id))
    db.commit()
    path = f"/articles/{aid}"
    api.ok(api.post(path + "/publish"))
    expected = [
        {"insightId": first["id"], "memberId": members[1]["memberId"], "name": "김응철", "record": "통산 10도움", "remaining": 1},
        {"insightId": second["id"], "memberId": members[2]["memberId"], "name": "유창우", "record": "통산 50경기 출전", "remaining": 1},
        {"insightId": third["id"], "memberId": members[3]["memberId"], "name": "윤영문", "record": "통산 10골", "remaining": 2},
    ]
    public = api.ok(api.get(path, admin=False))
    all_expected = [
        {"insightId": used["id"], "memberId": members[0]["memberId"], "name": "본문 선수", "record": "통산 10골", "remaining": 1},
        *expected,
    ]
    assert public["milestones"] == all_expected
    assert public["unusedMilestones"] == expected
    assert "requestJson" not in public
    assert all("importance" not in row and "facts" not in row for row in public["milestones"])
    assert api.ok(api.get(path))["milestones"] == all_expected
    # 현재 선수 정보가 바뀌어도 당시 기사의 표는 스냅샷을 유지한다.
    api.ok(api.patch(f"/members/{members[1]['memberId']}", {"name": "변경한 이름"}))
    assert api.ok(api.get(path, admin=False))["milestones"] == all_expected
    assert api.ok(api.get(path, admin=False))["unusedMilestones"] == expected
    listed = api.ok(api.get("/articles", admin=False))[0]
    assert "milestones" not in listed and "unusedMilestones" not in listed


@pytest.mark.parametrize("article_type,payload", [
    ("PRE_MATCH", None), ("PRE_MATCH", {}), ("PRE_MATCH", {"insights": None}),
    ("PRE_MATCH", {"insights": []}),
    ("PRE_MATCH", {"insights": [_milestone(1000000, 1, "선수")], "milestoneInsights": []}),
    ("SESSION_RECAP", {"insights": []}),
    ("MONTHLY_MVP", {"insights": []}),
    ("NOTICE", None),
], ids=["missing", "empty", "null-insights", "no-insights", "snapshot-empty", "recap", "monthly", "notice"])
def test_articles_without_milestones_return_empty(make_club, db, article_type, payload, request):
    api = make_club("milestonesempty" + request.node.callspec.id)
    article = _preview(api)
    a = db.get(AiArticle, article["articleId"])
    a.article_type, a.request_json = article_type, payload
    db.commit()
    result = api.ok(api.get(f"/articles/{a.article_id}"))
    assert result["milestones"] == result["unusedMilestones"] == []


@pytest.mark.parametrize("snapshot_key", ["insights", "milestoneInsights"])
def test_malformed_milestones_do_not_break_article(make_club, db, snapshot_key):
    api = make_club("milestoneslegacy" + snapshot_key.lower())
    article = _preview(api)
    member = api.ok(api.get("/members"))[0]
    valid = _milestone(1000000, member["memberId"], member["name"])
    invalid = [None, 1, {"type": "MILESTONE_EXPECTED"}, {**valid, "id": "1000000"}]
    for field, value in [("remaining", 0), ("remaining", -1), ("remaining", "1"), ("remaining", True),
                         ("milestone", None), ("metric", "unknown"), ("current", 999), ("member", None)]:
        item = deepcopy(valid)
        item["facts"][field] = value
        if field == "member":
            item["subject"] = None
        invalid.append(item)
    a = db.get(AiArticle, article["articleId"])
    a.request_json = {snapshot_key: [*invalid, valid, deepcopy(valid)]}
    db.commit()
    rows = api.ok(api.get(f"/articles/{a.article_id}"))["milestones"]
    assert len(rows) == 1
    assert rows[0]["record"] == "통산 10골" and rows[0]["remaining"] == 1


def _editable_article(api, db):
    article = _preview(api)
    insight_rows = list(db.scalars(select(Insight).where(Insight.session_id == article["sessionId"])
                                   .order_by(Insight.insight_id)))
    assert len(insight_rows) >= 3
    members = api.ok(api.get("/members"))
    milestones = [_milestone(insight_rows[i].insight_id, members[i]["memberId"], members[i]["name"])
                  for i in range(2)]
    a = db.get(AiArticle, article["articleId"])
    a.request_json = {"insights": milestones}
    db.execute(delete(AiArticleInsight).where(AiArticleInsight.article_id == a.article_id))
    db.add(AiArticleInsight(article_id=a.article_id, insight_id=milestones[0]["id"]))
    db.commit()
    return article, milestones, insight_rows[2].insight_id


def test_editing_used_facts_keeps_full_milestone_table_and_preserves_old_clients(make_club, db):
    api = make_club("milestonesedit")
    article, milestones, _ = _editable_article(api, db)
    path = f"/articles/{article['articleId']}"
    body = {"title": "수정한 기사", "summary": "수정 요약", "content": "선택한 기록을 다룬 기사"}
    selected = milestones[1]["id"]
    result = api.ok(api.patch(path, {**body, "usedInsightIds": [selected, selected]}))
    assert result["usedInsightIds"] == [selected]
    expected_ids = [m["id"] for m in milestones]
    assert [m["insightId"] for m in result["milestones"]] == expected_ids
    assert [m["insightId"] for m in result["unusedMilestones"]] == [milestones[0]["id"]]
    # 기존 편집 클라이언트가 필드를 보내지 않거나 null을 보내면 기존 선택을 보존한다.
    assert api.ok(api.patch(path, body))["usedInsightIds"] == [selected]
    assert api.ok(api.patch(path, {**body, "usedInsightIds": None}))["usedInsightIds"] == [selected]
    cleared = api.ok(api.patch(path, {**body, "usedInsightIds": []}))
    assert cleared["usedInsightIds"] == []
    assert [m["insightId"] for m in cleared["milestones"]] == expected_ids
    assert [m["insightId"] for m in cleared["unusedMilestones"]] == [m["id"] for m in milestones]


def test_milestones_outside_ai_limit_survive_generation_and_regeneration(make_club, db):
    api = make_club("milestoneslimit")
    original = _preview(api)
    api.ok(api.patch("/admin/config", {"values": {"WIRE_MAX_INSIGHTS": 1}}))
    s = db.get(ClubSession, original["sessionId"])
    club = db.get(Club, s.club_id)
    members = api.ok(api.get("/members"))
    primary = db.scalar(select(Insight).where(Insight.session_id == s.session_id).order_by(Insight.insight_id))
    primary.importance = 100
    milestones = []
    for i, member in enumerate(members[:2]):
        facts = _milestone(1, member["memberId"], member["name"], "assists", 10, i + 1)["facts"]
        row = Insight(club_id=club.club_id, session_id=s.session_id, member_id=member["memberId"],
                      insight_type="MILESTONE_EXPECTED", category="MILESTONE", phase="PRE", importance=10 - i,
                      facts_json=facts, rule_version="milestone_expected_v1")
        db.add(row)
        milestones.append(row)
    db.flush()
    article = create_article(db, club, s, "PRE_MATCH", [primary, *milestones])
    db.commit()
    run_generation(article.article_id)
    result = api.ok(api.get(f"/articles/{article.article_id}"))
    assert [i["id"] for i in result["requestJson"]["insights"]] == [primary.insight_id]
    expected_ids = [m.insight_id for m in milestones]
    assert [m["insightId"] for m in result["milestones"]] == expected_ids
    assert [m["remaining"] for m in result["milestones"]] == [1, 2]
    # 나중의 Insight 변경·다시 쓰기로 과거 표의 남은 수가 바뀌면 안 된다.
    milestones[0].facts_json = {**milestones[0].facts_json, "current": 5, "remaining": 5}
    db.commit()
    regenerated = api.ok(api.post(f"/articles/{article.article_id}/regenerate"), 201)
    regenerated = api.ok(api.get(f"/articles/{regenerated['articleId']}"))
    assert regenerated["milestones"] == result["milestones"]
    api.ok(api.post(f"/articles/{regenerated['articleId']}/publish"))
    public = api.ok(api.get(f"/articles/{regenerated['articleId']}", admin=False))
    assert public["milestones"] == result["milestones"]


def test_invalid_used_facts_are_rejected_without_partial_mutations(make_club, db):
    api = make_club("milestoneseditinvalid")
    article, milestones, unsubmitted = _editable_article(api, db)
    path = f"/articles/{article['articleId']}"
    original = api.ok(api.get(path))
    body = {"title": "저장되면 안 되는 제목", "summary": "저장되면 안 되는 요약", "content": "저장되면 안 되는 본문"}
    # 같은 일정의 사실이어도 기사 생성 당시 전달하지 않았다면 선택할 수 없다.
    rejected = api.patch(path, {**body, "usedInsightIds": [milestones[0]["id"], unsubmitted]})
    assert rejected.status_code == 400 and rejected.json()["error"]["code"] == "INVALID_ARTICLE_INSIGHTS"
    # 다른 클럽의 사실은 오래된/손상된 요청 스냅샷에 들어 있어도 선택할 수 없다.
    other = make_club("milestoneseditforeign")
    foreign = _preview(other)
    foreign_id = db.scalar(select(Insight.insight_id).where(Insight.session_id == foreign["sessionId"]))
    a = db.get(AiArticle, article["articleId"])
    a.request_json = {"insights": [*milestones, _milestone(foreign_id, 1, "다른 클럽 선수")]}
    db.commit()
    assert api.patch(path, {**body, "usedInsightIds": [foreign_id]}).status_code == 400
    for field in ("title", "summary", "content", "usedInsightIds"):
        assert api.ok(api.get(path))[field] == original[field]
    # 같은 클럽의 다른 일정 역시 이번 기사에 연결할 수 없다.
    ids = [m["memberId"] for m in api.ok(api.get("/members"))]
    sid = api.ok(api.post("/sessions", {"sessionDate": "2026-12-12"}), 201)["sessionId"]
    api.ok(api.post(f"/sessions/{sid}/members", {"memberIds": ids}))
    gen = api.ok(api.post(f"/sessions/{sid}/teams/generate", {"teamCount": 2}))
    api.ok(api.post(f"/sessions/{sid}/teams/confirm", {"generationId": gen["generationId"]}))
    other_session_id = db.scalar(select(Insight.insight_id).where(Insight.session_id == sid))
    a.request_json = {"insights": [*milestones, _milestone(other_session_id, ids[0], "다른 일정 선수")]}
    db.commit()
    assert api.patch(path, {**body, "usedInsightIds": [other_session_id]}).status_code == 400
    # 요청 목록 길이와 원소 형식도 검증한다.
    assert api.patch(path, {**body, "usedInsightIds": [milestones[0]["id"]] * 101}).status_code == 422
    assert api.patch(path, {**body, "usedInsightIds": [True]}).status_code == 422
    assert api.patch(path, {**body, "usedInsightIds": [999999999]}).status_code == 400
    after = api.ok(api.get(path))
    for field in ("title", "summary", "content", "usedInsightIds"):
        assert after[field] == original[field]
