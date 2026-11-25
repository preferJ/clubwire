"""이전 상승률 순위는 유지하되 월 마감으로 MVP를 자동 수여하지 않는다.
점수 자체는 어디에도 노출하지 않는다. 2026-11부터의 월간 포인트제는 test_monthly_mvp_points.py."""
import json
from datetime import date

import pytest
from sqlalchemy import select

from app.core.database import SessionLocal
from app.core.timeutil import local_today, month_range, prev_month_start
from app.models import AiArticle, MemberTitle, TitleType
from app.services import mvp_service
from app.services.common import get_club_by_slug


@pytest.fixture(autouse=True)
def rise_rule(monkeypatch):
    """이 파일은 시계와 상관없이 이전 방식(상승률)으로 고정한다."""
    monkeypatch.setattr(mvp_service, "POINTS_FROM", date(2999, 1, 1))


def _play_session(api, sid, member_ids, games=2):
    """참석 → 2팀 편성 → 확정 → 매 경기 첫 팀이 1:0 승리 후 경기 확정(점수 변화가 생기게)."""
    api.ok(api.post(f"/sessions/{sid}/members", {"memberIds": member_ids}))
    gen = api.ok(api.post(f"/sessions/{sid}/teams/generate", {"teamCount": 2}))
    api.ok(api.post(f"/sessions/{sid}/teams/confirm", {"generationId": gen["generationId"]}))
    for _ in range(games):
        m = api.next_match(sid)
        mid = m["matchId"]
        api.ok(api.post(f"/matches/{mid}/start"))
        team = m["teamA"]["sessionTeamId"]
        scorer = api.ok(api.get(f"/matches/{mid}"))["teamA"]["members"][0]["memberId"]
        api.ok(api.post(f"/matches/{mid}/goals", {"teamId": team, "scorerMemberId": scorer}))
        api.ok(api.post(f"/matches/{mid}/end"))
        api.ok(api.post(f"/matches/{mid}/finalize"))  # 점수 변화는 확정된 경기만


def _expected(api, member_ids, min_sessions_of):
    """DB 이력으로 직접 계산한 상승률(%) — 자격(일정 2회 이상) 충족 + 상승한 선수만."""
    out = {}
    for mid in member_ids:
        h = api.rating_history_db(mid)
        if not h or min_sessions_of[mid] < 2:
            continue
        pct = round((h[-1]["after"] - h[0]["before"]) / h[0]["before"] * 100, 2)
        if pct > 0:
            out[mid] = pct
    return out


def test_month_close_keeps_rise_rankings_without_automatic_mvp(make_club):
    api = make_club("mvp")
    ids = [api.ok(api.post("/members", {"name": n}), 201)["memberId"]
           for n in ("홍길동", "김철수", "이영희", "박민수", "최지훈", "정우성")]
    month = prev_month_start(local_today("Asia/Seoul"))
    s1 = api.ok(api.post("/sessions", {"sessionDate": month.replace(day=3).isoformat()}), 201)["sessionId"]
    s2 = api.ok(api.post("/sessions", {"sessionDate": month.replace(day=10).isoformat()}), 201)["sessionId"]
    _play_session(api, s1, ids)
    _play_session(api, s2, ids[:5])
    api.ok(api.post(f"/sessions/{s1}/close"))
    api.ok(api.post(f"/sessions/{s2}/close"))
    assert not [a for a in api.ok(api.get("/titles/awards")) if a["titleCode"] == "MONTHLY_MVP"]
    assert not [a for a in api.ok(api.get("/articles")) if a["articleType"] == "MONTHLY_MVP"]
    # 순위 자격(일정 2회)을 충족하지 않은 선수도 관리자가 선정할 수 있다.
    result = api.ok(api.post(f"/members/{ids[5]}/monthly-mvp", {"month": month.strftime("%Y-%m")}))
    assert result["winners"] == [{"memberId": ids[5], "name": "정우성"}]
    article = api.ok(api.get(f"/articles/{result['articleId']}", admin=False))
    assert article["sessionId"] is None and article["status"] == "PUBLISHED"
    assert "정우성" in article["title"] and "관리자" in article["content"]
    assert "상승률 1위" not in article["content"]
    awards = [a for a in api.ok(api.get("/titles/awards")) if a["titleCode"] == "MONTHLY_MVP"]
    assert len(awards) == 1 and awards[0]["memberId"] == ids[5]
    with SessionLocal() as db:
        club = get_club_by_slug(db, "mvp")
        assert mvp_service.close_due_month(db, club) == []
    assert len([a for a in api.ok(api.get("/titles/awards")) if a["titleCode"] == "MONTHLY_MVP"]) == 1


def test_mvp_race_candidates_only_percent(make_club):
    api = make_club("race")
    ids = [api.ok(api.post("/members", {"name": f"R{i}"}), 201)["memberId"] for i in range(6)]
    month = prev_month_start(local_today("Asia/Seoul"))
    s1 = api.ok(api.post("/sessions", {"sessionDate": month.replace(day=4).isoformat()}), 201)["sessionId"]
    s2 = api.ok(api.post("/sessions", {"sessionDate": month.replace(day=11).isoformat()}), 201)["sessionId"]
    _play_session(api, s1, ids)
    _play_session(api, s2, ids[:5])

    # 그 달 중간(마감 전): 후보 1~3위, 상승률만. 자격 미달(1회) 제외. 점수 키 없음
    with SessionLocal() as s:
        club = get_club_by_slug(s, "race")
        race = mvp_service.mvp_race(s, club, today=month.replace(day=20))
    assert race["month"] == month.strftime("%Y-%m") and race["minSessions"] == 2 and race["lastMonth"] is None
    assert race["basis"] == "rise"
    expected = _expected(api, ids, {m: (2 if m in ids[:5] else 1) for m in ids})
    top = sorted(expected.values(), reverse=True)[:3]
    assert [c["risePercent"] for c in race["candidates"]] == top
    assert all(set(c) == {"rank", "memberId", "name", "risePercent", "sessions", "games"} for c in race["candidates"])
    assert ids[5] not in [c["memberId"] for c in race["candidates"]]
    assert race["candidates"] and race["candidates"][0]["rank"] == 1

    # 공개 API(이번 달 기준): 형태 확인
    live = api.ok(api.get("/stats/mvp-race", admin=False))
    assert set(live) == {"month", "minSessions", "basis", "candidates", "lastMonth"} and live["basis"] == "rise"
    assert "rating" not in json.dumps(live).lower()

    # 설정으로 자격 변경(1회 이상) → 1회 출전 선수도 후보
    api.ok(api.patch("/admin/config", {"values": {"MONTHLY_MVP_MIN_SESSIONS": 1}}))
    with SessionLocal() as s:
        club = get_club_by_slug(s, "race")
        race1 = mvp_service.mvp_race(s, club, today=month.replace(day=20))
        allc = mvp_service.ranking(s, club.club_id, *month_range(month), 1)
    assert len(allc) >= len(expected) and race1["minSessions"] == 1


def test_month_helpers():
    assert month_range(date(2026, 2, 14)) == (date(2026, 2, 1), date(2026, 2, 28))
    assert month_range(date(2026, 12, 31)) == (date(2026, 12, 1), date(2026, 12, 31))
    assert prev_month_start(date(2026, 1, 1)) == date(2025, 12, 1)
