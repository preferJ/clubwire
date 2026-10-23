"""이달의 MVP: 그 달 실력 점수 상승률 1위 → 월 마감 때 타이틀 + 기사(바로 게시). 점수 자체는 어디에도 노출하지 않는다."""
import json
from datetime import date

from sqlalchemy import select

from app.core.database import SessionLocal
from app.core.timeutil import local_today, month_range, prev_month_start
from app.models import AiArticle, MemberTitle, TitleType
from app.services import mvp_service
from app.services.common import get_club_by_slug


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


def test_monthly_mvp_close_award_and_article(make_club):
    api = make_club("mvp")
    ids = [api.ok(api.post("/members", {"name": n}), 201)["memberId"]
           for n in ("홍길동", "김철수", "이영희", "박민수", "최지훈", "정우성")]
    month = prev_month_start(local_today("Asia/Seoul"))  # 지난달 = 월 마감 대상
    start, end = month_range(month)
    s1 = api.ok(api.post("/sessions", {"sessionDate": month.replace(day=3).isoformat()}), 201)["sessionId"]
    s2 = api.ok(api.post("/sessions", {"sessionDate": month.replace(day=10).isoformat()}), 201)["sessionId"]
    s3 = api.ok(api.post("/sessions", {"sessionDate": month.replace(day=17).isoformat()}), 201)["sessionId"]

    _play_session(api, s1, ids)            # 6명
    _play_session(api, s2, ids[:5])        # 정우성은 1회만 → 후보 자격 없음
    api.ok(api.post(f"/sessions/{s1}/close"))

    def mvp_titles():
        with SessionLocal() as s:
            club = get_club_by_slug(s, "mvp")
            t = s.scalar(select(TitleType).where(TitleType.club_id == club.club_id, TitleType.title_code == "MONTHLY_MVP"))
            return list(s.scalars(select(MemberTitle).where(MemberTitle.title_type_id == t.title_type_id))), club

    # [일정마감]의 주간 자동 타이틀 계산은 이달의 MVP를 건드리지 않음 / 그 달 열린 일정이 있으면 기다림
    assert mvp_titles()[0] == []

    # 남은 일정 취소 → 마지막 일정 [일정마감] 때 지난달이 끝났으므로 바로 월 마감(동기 생성 설정)
    api.ok(api.post(f"/sessions/{s3}/cancel"))
    api.ok(api.post(f"/sessions/{s2}/close"))
    titles, club = mvp_titles()
    expected = _expected(api, ids, {m: (2 if m in ids[:5] else 1) for m in ids})
    best = max(expected.values())
    assert sorted(t.member_id for t in titles) == sorted(m for m, v in expected.items() if v == best)
    assert ids[5] not in [t.member_id for t in titles]
    t0 = titles[0]
    assert (t0.period_start, t0.period_end, t0.session_id) == (start, end, s2)  # 기사·타이틀은 그 달 마지막 일정에
    assert t0.facts_json["metric"] == "risePercent" and t0.facts_json["value"] == best and t0.facts_json["sessions"] == 2

    # 기사: 게시 설정(기본 MANUAL)과 상관없이 바로 게시 · '이달의 MVP' 태그 · 점수 자체는 없음
    arts = api.ok(api.get("/articles", admin=False))
    mvp_art = next(a for a in arts if a["articleType"] == "MONTHLY_MVP")
    assert "이달의 MVP" in mvp_art["tags"] and mvp_art["sessionId"] == s2
    detail = api.ok(api.get(f"/articles/{mvp_art['articleId']}", admin=False))
    text = f"{detail['title']}\n{detail['summary']}\n{detail['content']}"
    names = {m["memberId"]: m["name"] for m in api.ok(api.get("/members"))}
    assert all(names[t.member_id] in detail["title"] for t in titles)
    assert f"{best:.1f}%" in text and "특히 많이 오른 경기" in text and "가장 크게 오른 날" in text
    assert "레이팅" not in text and "rating" not in text.lower()
    with SessionLocal() as s:
        payload = json.dumps(s.get(AiArticle, mvp_art["articleId"]).request_json, ensure_ascii=False)
    for mid in ids:
        for h in api.rating_history_db(mid):  # 점수(예: 1010.3)는 AI 입력에도 넣지 않음
            assert f"{h['after']:.1f}" not in payload and f"{h['before']:.2f}" not in payload
    assert "bestMatches" in payload and "runnersUp" in payload

    # 수상 내역(공개)에 표시
    awards = api.ok(api.get("/titles/awards", admin=False))
    assert {a["titleName"] for a in awards if a["titleCode"] == "MONTHLY_MVP"} == {"이달의 MVP"}

    # 한 달은 한 번만: 다시 돌려도, 관리자가 수여를 취소해도 다시 만들지 않음
    with SessionLocal() as s:
        club = get_club_by_slug(s, "mvp")
        assert mvp_service.close_due_month(s, club) == []
    api.ok(api.post(f"/titles/awards/{t0.member_title_id}/cancel"))
    with SessionLocal() as s:
        club = get_club_by_slug(s, "mvp")
        assert mvp_service.close_due_month(s, club) == []


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
    expected = _expected(api, ids, {m: (2 if m in ids[:5] else 1) for m in ids})
    top = sorted(expected.values(), reverse=True)[:3]
    assert [c["risePercent"] for c in race["candidates"]] == top
    assert all(set(c) == {"rank", "memberId", "name", "risePercent", "sessions", "games"} for c in race["candidates"])
    assert ids[5] not in [c["memberId"] for c in race["candidates"]]
    assert race["candidates"] and race["candidates"][0]["rank"] == 1

    # 공개 API(이번 달 기준): 형태 확인
    live = api.ok(api.get("/stats/mvp-race", admin=False))
    assert set(live) == {"month", "minSessions", "candidates", "lastMonth"}
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
