"""재편성은 명단 순서/팀 이름이 아닌 실제 동료 구성을 바꾼다."""
from app.core.club_config import ClubConfig
from app.strategies.team_generation import MemberInput, partition_key, team_generator


def result_key(result):
    return partition_key([t.member_ids for t in result.teams], [t.guest_ids for t in result.teams])


def api_key(result):
    return partition_key([[m['memberId'] for m in t['members']] for t in result['teams']],
                         [[g['guestId'] for g in t['guests']] for t in result['teams']])


def test_reshuffle_changes_unique_best_partition_without_losing_players():
    cfg = ClubConfig.defaults()
    ratings = [900, 913, 947, 981, 1002, 1041, 1087, 1129]
    members = [MemberInput(i, rating, .5) for i, rating in enumerate(ratings, 1)]
    previous = None
    for seed in range(1, 7):
        result = team_generator.generate(members, [], 2, lambda a, b: (0, 0), cfg,
                                         seed=seed, previous_partition=previous)
        current = result_key(result)
        assert current != previous
        assert result.spread_percent <= cfg['TEAM_RATING_TOLERANCE_PERCENT']
        assert sorted(mid for t in result.teams for mid in t.member_ids) == list(range(1, 9))
        previous = current


def test_guests_also_change_teammates():
    cfg = ClubConfig.defaults()
    first = team_generator.generate([], list(range(1, 9)), 2, lambda a, b: (0, 0), cfg, seed=1)
    second = team_generator.generate([], list(range(1, 9)), 2, lambda a, b: (0, 0), cfg,
                                     seed=2, previous_partition=result_key(first))
    assert result_key(second) != result_key(first)
    assert sorted(gid for t in second.teams for gid in t.guest_ids) == list(range(1, 9))
    assert [t.headcount for t in second.teams] == [4, 4]


def test_partition_ignores_labels_order_but_not_member_guest_identity():
    first = partition_key([[1, 2], [3]], [[3], [1, 2]])
    assert first == partition_key([[3], [2, 1]], [[2, 1], [3]])
    assert first != partition_key([[1, 3], [2]], [[2], [1, 3]])


def test_only_balanced_partition_is_reported_unchanged():
    cfg = ClubConfig({**ClubConfig.defaults().snapshot(), 'TEAM_RATING_TOLERANCE_PERCENT': 0}, 1)
    members = [MemberInput(i, rating, .5) for i, rating in enumerate([900, 910, 1000, 1010], 1)]
    first = team_generator.generate(members, [], 2, lambda a, b: (0, 0), cfg, seed=1)
    second = team_generator.generate(members, [], 2, lambda a, b: (0, 0), cfg,
                                     seed=2, previous_partition=result_key(first))
    assert second.spread_percent == 0
    assert result_key(second) == result_key(first)
    assert second.extra['reshuffleChanged'] is False


def test_generate_api_remembers_previous_preview_and_seed_still_reproduces(make_club):
    api = make_club('reshuffle')
    ids = [api.ok(api.post('/members', {'name': f'선수{i}', 'initialRating': rating}), 201)['memberId']
           for i, rating in enumerate([900, 913, 947, 981, 1002, 1041, 1087, 1129])]
    sid = api.ok(api.post('/sessions', {'sessionDate': '2026-11-15'}), 201)['sessionId']
    api.ok(api.post(f'/sessions/{sid}/members', {'memberIds': ids}))
    path = f'/sessions/{sid}/teams/generate'
    previous = api.ok(api.post(path, {'teamCount': 2}))
    assert previous['reshuffleChanged'] is None
    for _ in range(4):
        current = api.ok(api.post(path, {'teamCount': 2}))
        assert api_key(current) != api_key(previous)
        assert current['reshuffleChanged'] is True
        assert current['spreadPercent'] <= 1
        previous = current
    seeded = [api.ok(api.post(path, {'teamCount': 2, 'seed': 123})) for _ in range(2)]
    assert api_key(seeded[0]) == api_key(seeded[1])
    different_count = api.ok(api.post(path, {'teamCount': 3}))
    assert different_count['reshuffleChanged'] is None
    api.ok(api.post(f'/sessions/{sid}/teams/confirm', {'generationId': previous['generationId']}))
    teams = api.ok(api.get(f'/sessions/{sid}/teams'))
    assert api_key(teams) == api_key(previous)


def test_away_preview_and_normal_reshuffle_can_be_switched(make_club):
    api = make_club('reshuffleaway')
    ids = [api.ok(api.post('/members', {'name': f'원정선수{i}'}), 201)['memberId'] for i in range(6)]
    sid = api.ok(api.post('/sessions', {'sessionDate': '2026-11-16'}), 201)['sessionId']
    api.ok(api.post(f'/sessions/{sid}/members', {'memberIds': ids}))
    oid = api.ok(api.post('/opponents', {'name': '상대팀'}), 201)['opponentId']
    path = f'/sessions/{sid}/teams/generate'
    api.ok(api.post(path, {'teamCount': 2}))
    away = api.ok(api.post(path, {'teamCount': 1, 'opponentId': oid}))
    assert away['balanceLabel'] == '원정 경기'
    assert away['opponentId'] == oid
    assert away['reshuffleChanged'] is None
    assert sorted(m['memberId'] for m in away['teams'][0]['members']) == sorted(ids)
    normal = api.ok(api.post(path, {'teamCount': 2}))
    assert normal['reshuffleChanged'] is None
    again = api.ok(api.post(path, {'teamCount': 2}))
    assert again['reshuffleChanged'] is True
    assert api_key(normal) != api_key(again)
    # 원정 편성 확정에서도 우리 팀 전원과 선수 없는 상대 팀을 그대로 보존한다.
    confirmed = api.ok(api.post(f'/sessions/{sid}/teams/confirm', {'generationId': away['generationId']}))
    assert confirmed['away'] is True
    ours = next(t for t in confirmed['teams'] if not t['opponent'])
    opponent = next(t for t in confirmed['teams'] if t['opponent'])
    assert sorted(m['memberId'] for m in ours['members']) == sorted(ids)
    assert opponent['members'] == []
