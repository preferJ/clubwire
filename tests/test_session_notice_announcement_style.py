"""일정별 공지(SESSION.NOTICE) + 상단 공지 스타일(CLUB.ANNOUNCEMENT_STYLE) — DECISIONS 3-19.

- 일정별 공지: 일정 만들 때 · 일정 수정으로 입력(관리자), 줄바꿈 허용 · 최대 500자, 빈 값이면 지움, 생략하면 유지.
  일정 목록 · 상세(공개)에 내려가 일정 화면과 메인 팀 편성 카드에서 팀 밸런스 안내 위에 표시
- 상단 공지 스타일: default / highlight / accent / alert, 스타일만 바꾸면 공지 문구 수정 시각은 그대로
"""


def test_session_notice_create_update_clear(make_club):
    api = make_club("snotice")
    # 만들 때 같이 입력: 앞뒤 공백 · 줄 끝 공백 정리, 빈 줄은 하나로
    s = api.ok(api.post("/sessions", {"sessionDate": "2027-05-08", "title": "정기 풋살",
                                      "notice": "  9시 50분까지 집합  \n\n\n흰색 상의 지참 \n"}), 201)
    sid = s["sessionId"]
    assert s["notice"] == "9시 50분까지 집합\n\n흰색 상의 지참"
    # 공개 조회(목록 · 상세)에 그대로
    assert api.ok(api.get(f"/sessions/{sid}", admin=False))["notice"] == s["notice"]
    assert next(x for x in api.ok(api.get("/sessions", admin=False)) if x["sessionId"] == sid)["notice"] == s["notice"]
    # 공지 없이 만든 일정은 null
    other = api.ok(api.post("/sessions", {"sessionDate": "2027-05-15"}), 201)
    assert other["notice"] is None

    # 수정: 관리자만, 다른 항목만 고치면 공지는 그대로
    assert api.patch(f"/sessions/{sid}", {"notice": "변경"}, admin=False).status_code == 401
    assert api.ok(api.patch(f"/sessions/{sid}", {"location": "강변 구장"}))["notice"] == s["notice"]
    changed = api.ok(api.patch(f"/sessions/{sid}", {"notice": "주차는 B동 뒤편"}))
    assert changed["notice"] == "주차는 B동 뒤편" and changed["location"] == "강변 구장"
    # 500자까지
    assert api.patch(f"/sessions/{sid}", {"notice": "가" * 501}).status_code == 422
    assert len(api.ok(api.patch(f"/sessions/{sid}", {"notice": "가" * 500}))["notice"]) == 500
    # 빈 문자열 · 공백만 · null이면 지움
    assert api.ok(api.patch(f"/sessions/{sid}", {"notice": "   \n "}))["notice"] is None
    api.ok(api.patch(f"/sessions/{sid}", {"notice": "다시"}))
    assert api.ok(api.patch(f"/sessions/{sid}", {"notice": None}))["notice"] is None

    # 팀 확정 뒤에도 수정 가능(확정 후 안내가 가장 많이 쓰임), 마감한 일정은 수정 불가
    ids = [api.ok(api.post("/members", {"name": f"N{i}"}), 201)["memberId"] for i in range(4)]
    api.ok(api.post(f"/sessions/{sid}/members", {"memberIds": ids}))
    gen = api.ok(api.post(f"/sessions/{sid}/teams/generate", {"teamCount": 2}))
    conf = api.ok(api.post(f"/sessions/{sid}/teams/confirm", {"generationId": gen["generationId"]}))
    assert conf["status"] == "CONFIRMED" and conf["notice"] is None
    assert api.ok(api.patch(f"/sessions/{sid}", {"notice": "조끼는 A팀이 챙겨 주세요"}))["notice"] == "조끼는 A팀이 챙겨 주세요"
    m = api.next_match(sid)
    api.ok(api.post(f"/matches/{m['matchId']}/start"))
    api.ok(api.post(f"/matches/{m['matchId']}/end"))
    api.ok(api.post(f"/sessions/{sid}/close"))
    assert api.patch(f"/sessions/{sid}", {"notice": "마감 후"}).status_code == 409
    assert api.ok(api.get(f"/sessions/{sid}", admin=False))["notice"] == "조끼는 A팀이 챙겨 주세요"  # 지난 공지는 남는다


def test_announcement_style_presets(make_club):
    api = make_club("nstyle")
    api.ok(api.patch("/admin/content", {"announcement": "토요일 8시 시작", "announcementSize": "large"}))
    before = api.ok(api.get("/content", admin=False))
    assert before["announcementStyle"] == "default"
    for style in ("highlight", "accent", "alert"):
        got = api.ok(api.patch("/admin/content", {"announcementStyle": style}))
        assert got["announcementStyle"] == style
        # 스타일만 바꾸면 문구 · 크기 · 문구 수정 시각은 그대로
        assert (got["announcement"], got["announcementSize"]) == ("토요일 8시 시작", "large")
        assert got["announcementUpdatedAt"] == before["announcementUpdatedAt"]
    assert api.ok(api.get("/content", admin=False))["announcementStyle"] == "alert"
    assert api.patch("/admin/content", {"announcementStyle": "blink"}).status_code == 422
    assert api.patch("/admin/content", {"announcementStyle": "accent"}, admin=False).status_code == 401
    # 문구만 고치면 스타일 유지, null이면 기본으로
    assert api.ok(api.patch("/admin/content", {"announcement": "일요일로 변경"}))["announcementStyle"] == "alert"
    assert api.ok(api.patch("/admin/content", {"announcementStyle": None}))["announcementStyle"] == "default"
