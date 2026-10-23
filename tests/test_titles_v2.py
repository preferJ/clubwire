"""이달의 득점왕 · 도움왕(월 마감) + 연속 참가 10 · 20 · 30 · 40 · 50회([일정마감], 참석 명단 기준)."""
from datetime import date, timedelta

from sqlalchemy import delete, select

from app.core.database import SessionLocal
from app.core.timeutil import local_today, month_range, prev_month_start
from app.models import AiArticle, MemberTitle, TitleType
from app.services import mvp_service
from app.services.common import get_club_by_slug
from app.services.history import load_history, member_totals


def _titles(slug: str, code_prefix: str) -> list[tuple[str, int, int | None, dict]]:
    with SessionLocal() as s:
        club = get_club_by_slug(s, slug)
        rows = s.execute(select(TitleType.title_code, MemberTitle.member_id, MemberTitle.session_id, MemberTitle.facts_json)
                         .join(TitleType, TitleType.title_type_id == MemberTitle.title_type_id)
                         .where(MemberTitle.club_id == club.club_id, MemberTitle.cancelled_yn.is_(False),
                                TitleType.title_code.like(f"{code_prefix}%"))
                         .order_by(MemberTitle.member_title_id)).all()
    return [tuple(r) for r in rows]


def _session(api, d: date, member_ids, matches=0):
    sid = api.ok(api.post("/sessions", {"sessionDate": d.isoformat()}), 201)["sessionId"]
    api.ok(api.post(f"/sessions/{sid}/members", {"memberIds": member_ids}))
    gen = api.ok(api.post(f"/sessions/{sid}/teams/generate", {"teamCount": 2}))
    api.ok(api.post(f"/sessions/{sid}/teams/confirm", {"generationId": gen["generationId"]}))
    for g in range(matches):
        m = api.next_match(sid)
        mid = m["matchId"]
        api.ok(api.post(f"/matches/{mid}/start"))
        team = m["teamA"]["sessionTeamId"] if g % 2 == 0 else m["teamB"]["sessionTeamId"]
        side = "teamA" if g % 2 == 0 else "teamB"
        ms = api.ok(api.get(f"/matches/{mid}"))[side]["members"]
        api.ok(api.post(f"/matches/{mid}/goals", {"teamId": team, "scorerMemberId": ms[0]["memberId"],
                                                  "assistMemberId": ms[1]["memberId"]}))
        api.ok(api.post(f"/matches/{mid}/end"))
        api.ok(api.post(f"/matches/{mid}/finalize"))
    return sid


def test_monthly_top_scorer_and_assist(make_club):
    api = make_club("mstat")
    ids = [api.ok(api.post("/members", {"name": f"S{i}"}), 201)["memberId"] for i in range(6)]
    month = prev_month_start(local_today("Asia/Seoul"))
    s1 = _session(api, month.replace(day=5), ids, matches=3)
    s2 = _session(api, month.replace(day=12), ids, matches=3)
    api.ok(api.post(f"/sessions/{s1}/close"))
    api.ok(api.post(f"/sessions/{s2}/close"))  # 지난달 마지막 일정 → 월 마감(MVP + 득점왕 · 도움왕)

    with SessionLocal() as s:
        club = get_club_by_slug(s, "mstat")
        tot = member_totals(load_history(s, club.club_id, session_ids=[s1, s2]))
    for code, metric in (("MONTHLY_TOP_SCORER", "goals"), ("MONTHLY_TOP_ASSIST", "assists")):
        best = max(getattr(v, metric) for v in tot.values())
        expect = sorted(m for m, v in tot.items() if getattr(v, metric) == best)
        got = [t for t in _titles("mstat", code)]
        assert sorted(t[1] for t in got) == expect and all(t[2] == s2 for t in got)
        assert all(t[3] == {"metric": metric, "value": best, "tied": len(expect) > 1} for t in got)

    awards = api.ok(api.get("/titles/awards", admin=False))
    assert {"이달의 득점왕", "이달의 도움왕", "이달의 MVP"} <= {a["titleName"] for a in awards}
    art = next(a for a in api.ok(api.get("/articles", admin=False)) if a["articleType"] == "MONTHLY_MVP")
    body = api.ok(api.get(f"/articles/{art['articleId']}"))
    assert "득점왕은" in body["content"] and "도움왕은" in body["content"]
    assert [x["titleName"] for x in body["requestJson"]["monthlyMvp"]["monthlyTitles"]] == ["이달의 득점왕", "이달의 도움왕"]

    # 배포 전에 MVP만 발표된 달: 득점왕 · 도움왕만 새로 채우고 기사는 다시 안 씀
    with SessionLocal() as s:
        club = get_club_by_slug(s, "mstat")
        tids = s.scalars(select(TitleType.title_type_id).where(
            TitleType.club_id == club.club_id, TitleType.title_code.in_(["MONTHLY_TOP_SCORER", "MONTHLY_TOP_ASSIST"]))).all()
        s.execute(delete(MemberTitle).where(MemberTitle.title_type_id.in_(tids)))
        s.commit()
        assert mvp_service.close_due_month(s, club) == []
        n_articles = s.scalar(select(AiArticle.article_id).where(AiArticle.club_id == club.club_id,
                                                                AiArticle.article_type == "MONTHLY_MVP").limit(2))
    assert n_articles and len(_titles("mstat", "MONTHLY_TOP_")) >= 2
    with SessionLocal() as s:  # 다시 돌려도 그대로
        club = get_club_by_slug(s, "mstat")
        before = len(_titles("mstat", "MONTHLY_"))
        assert mvp_service.close_due_month(s, club) == [] and len(_titles("mstat", "MONTHLY_")) == before


def test_attendance_streak_titles(make_club):
    """21번 일정(중간에 취소 1번). A·E·F 전부 참가 → 10 · 20회, B는 5번째 결석 → 15번째에 10회,
    C는 11번째 결석 → 10번째와 21번째에 두 번 10회. 취소된 일정은 세지도 끊지도 않음."""
    api = make_club("streak")
    names = ["A", "B", "C", "E", "F"]
    mid = {n: api.ok(api.post("/members", {"name": n}), 201)["memberId"] for n in names}
    d = date(2027, 1, 2)
    sids = []
    for i in range(1, 22):
        who = [n for n in names if not (n == "B" and i == 5) and not (n == "C" and i == 11)]
        sid = _session(api, d, [mid[n] for n in who])
        api.ok(api.post(f"/sessions/{sid}/close"))
        sids.append(sid)
        d += timedelta(days=7)
        if i == 3:  # 취소된 일정(참석 체크까지만 하고 취소)
            cid = api.ok(api.post("/sessions", {"sessionDate": d.isoformat()}), 201)["sessionId"]
            api.ok(api.post(f"/sessions/{cid}/members", {"memberIds": [mid["A"], mid["E"]]}))
            api.ok(api.post(f"/sessions/{cid}/cancel"))
            d += timedelta(days=7)

    got = {(code, m, sid) for code, m, sid, _ in _titles("streak", "ATTEND_STREAK_")}
    at = lambda k: sids[k - 1]  # noqa: E731  k번째 일정
    expect = set()
    for n in ("A", "E", "F"):
        expect |= {("ATTEND_STREAK_10", mid[n], at(10)), ("ATTEND_STREAK_20", mid[n], at(20))}
    expect |= {("ATTEND_STREAK_10", mid["B"], at(15))}
    expect |= {("ATTEND_STREAK_10", mid["C"], at(10)), ("ATTEND_STREAK_10", mid["C"], at(21))}
    assert got == expect
    assert all(f == {"metric": "attendStreak", "value": int(c.rsplit("_", 1)[1])}
               for c, _, _, f in _titles("streak", "ATTEND_STREAK_"))

    # 수상 내역(공개) · 선수별 타이틀 수
    awards = api.ok(api.get("/titles/awards", params={"memberId": mid["C"]}, admin=False))
    assert [a["titleName"] for a in awards] == ["연속 참가 10회", "연속 참가 10회"]
    assert {m["memberId"]: m["titleCount"] for m in api.ok(api.get("/stats/members", admin=False))}[mid["C"]] == 2

    # 수상 내역 조회: 상 별(코드, 'ATTEND_STREAK_' = 연속 참가 전부) · 기간 · 개수
    q = lambda **kw: api.ok(api.get("/titles/awards", params=kw, admin=False))  # noqa: E731
    assert len(q(titleCode="ATTEND_STREAK_")) == len(expect)
    assert {a["memberId"] for a in q(titleCode="ATTEND_STREAK_20")} == {mid["A"], mid["E"], mid["F"]}
    d10 = date(2027, 1, 2) + timedelta(days=7 * 10)  # 10번째 일정 날짜(3번째 뒤 취소 일정 1주 포함)
    assert {a["memberId"] for a in q(titleCode="ATTEND_STREAK_10", **{"from": d10.isoformat(), "to": d10.isoformat()})} \
        == {mid["A"], mid["C"], mid["E"], mid["F"]}
    assert len(q(limit=2)) == 2
    # 선수 상세: 자주 같은 팀 · 맞붙은 선수 개수(top)
    assert len(api.ok(api.get(f"/stats/members/{mid['A']}", params={"top": 2}, admin=False))["frequentTeammates"]) <= 2
