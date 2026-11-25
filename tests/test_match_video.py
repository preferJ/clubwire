from pathlib import Path
import shutil
import subprocess
from types import SimpleNamespace
from datetime import datetime, timedelta, timezone

import pytest
from app.core.config import settings
from app.core.database import SessionLocal
from app.models import MatchVideo
from app.services import video_service as svc


def test_motion_candidates_static_and_separated():
    frame = bytes([0]) * (160 * 90)
    bright = bytes([200]) * (160 * 90)
    assert svc.motion_candidates(frame * 20, 10) == []
    results = svc.motion_candidates(frame * 2 + bright * 12 + frame * 12, 10)
    assert len(results) == 2
    assert results[0]['videoSec'] == 11
    assert results[1]['videoSec'] == 17


def test_goal_mapping_accounts_for_pause_and_cancelled():
    now = datetime.now(timezone.utc)
    def event(kind, elapsed, seconds, cancelled=False, id=1):
        return SimpleNamespace(event_type=kind, elapsed_sec=elapsed, created_at=now + timedelta(seconds=seconds), cancelled_yn=cancelled, event_id=id)
    events = [event('START', 0, 0), event('PAUSE', 10, 10), event('RESUME', 10, 30),
              event('GOAL', 15, 35, id=4), event('GOAL', 20, 40, True, 5)]
    db = SimpleNamespace(scalars=lambda _: events)
    assert svc.snapshot_goals(db, 1, 5) == [{'eventId': 4, 'elapsedSec': 15, 'videoSec': 40.0}]


@pytest.mark.skipif(not shutil.which('ffmpeg'), reason='FFmpeg required')
def test_real_upload_extract_permissions_delete(make_club, tmp_path, monkeypatch):
    monkeypatch.setattr(settings, 'VIDEO_STORAGE_DIR', str(tmp_path / 'storage'))
    api = make_club('video-test')
    ids = [api.ok(api.post('/members', {'name': f'선수{i}'}), 201)['memberId'] for i in range(4)]
    sid = api.ok(api.post('/sessions', {'sessionDate': '2026-11-01'}), 201)['sessionId']
    api.ok(api.post(f'/sessions/{sid}/members', {'memberIds': ids}))
    generation = api.ok(api.post(f'/sessions/{sid}/teams/generate', {'teamCount': 2}))
    api.ok(api.post(f'/sessions/{sid}/teams/confirm', {'generationId': generation['generationId']}))
    match = api.next_match(sid)
    mid = match['matchId']
    api.ok(api.post(f'/matches/{mid}/start'))
    detail = api.ok(api.get(f'/matches/{mid}'))
    team = detail['teamA']
    goal = api.ok(api.post(f'/matches/{mid}/goals', {'teamId': team['sessionTeamId'], 'scorerMemberId': team['members'][0]['memberId'], 'elapsedSec': 1}))
    source = tmp_path / 'test.mp4'
    subprocess.run(['ffmpeg', '-v', 'error', '-f', 'lavfi', '-i', 'testsrc2=size=320x180:rate=10', '-t', '3', '-c:v', 'libx264', '-threads', '1', str(source)], check=True)
    base = f'/matches/{mid}/videos'
    assert api.get(base, admin=False).status_code == 401
    response = api.c.post(api.url(base), headers=api._h(True), content=source.read_bytes())
    v = api.ok(response, 202)
    results = api.ok(api.get(base))
    assert results[0]['status'] == 'READY', results
    clip = results[0]['clips'][0]
    assert clip['startSec'] == 0 and clip['endSec'] == 3
    path = f"{base}/{v['videoId']}/clips/{goal['eventId']}"
    assert api.get(path, admin=False).status_code == 401
    assert api.get(path).headers['content-type'] == 'video/mp4'
    other = make_club('video-other')
    assert other.get(base).status_code == 404
    assert other.get(path).status_code == 404
    with SessionLocal() as db:
        row = db.get(MatchVideo, v['videoId'])
        assert not (svc.folder(row.storage_key) / 'source').exists()
    api.ok(api.delete(f"{base}/{v['videoId']}"))
    assert api.ok(api.get(base)) == []
    assert api.get(path).status_code == 404
    # Invalid media does not leave the source on disk.
    invalid = api.c.post(api.url(base), headers=api._h(True), content=b'not a movie')
    api.ok(invalid, 202)
    assert api.ok(api.get(base))[0]['status'] == 'FAILED'
    monkeypatch.setattr(settings, 'VIDEO_MAX_MB', 1)
    assert api.c.post(api.url(base), headers=api._h(True), content=b'x' * (1024 * 1024 + 1)).status_code == 400
    assert not list((tmp_path / 'storage').rglob('source'))
