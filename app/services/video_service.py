"""관리자 영상 검토: 기록 기반 ±30초 클립 + 저해상도 프레임 차분 후보. 득점 판정 모델이 아니다."""
import json
import math
from pathlib import Path
import shutil
import subprocess
import threading

from sqlalchemy import select
from app.core.config import settings
from app.core.database import SessionLocal
from app.core.errors import BadRequest, NotFound
from app.models import MatchEvent, MatchVideo
from app.services.common import get_match

# 2GB 서버에서도 디코딩 작업을 한 번에 하나만 실행한다. 단일 uvicorn worker 사용.
PROCESS_LOCK = threading.Lock()


def folder(key):
    return Path(settings.VIDEO_STORAGE_DIR).resolve() / key


def require_tools():
    if not shutil.which('ffmpeg') or not shutil.which('ffprobe'):
        raise BadRequest('서버에 FFmpeg와 ffprobe를 설치해야 합니다.', 'VIDEO_TOOLS_MISSING')


def get_video(db, club_id, match_id, video_id):
    get_match(db, club_id, match_id)
    v = db.get(MatchVideo, video_id)
    if not v or v.match_id != match_id:
        raise NotFound('영상을 찾을 수 없습니다.')
    return v


def snapshot_goals(db, match_id, offset):
    events = list(db.scalars(select(MatchEvent).where(MatchEvent.match_id == match_id).order_by(MatchEvent.event_id)))
    start = next((e.created_at for e in events if e.event_type == 'START'), None)
    resumes = [e for e in events if e.event_type == 'RESUME' and e.elapsed_sec is not None]
    goals = []
    for e in events:
        if e.event_type != 'GOAL' or e.cancelled_yn or e.elapsed_sec is None:
            continue
        # 연속 촬영 기준: 경기 타이머가 정지했던 실제 시간을 포함한다.
        extra = 0
        for r in resumes:
            if start and r.elapsed_sec <= e.elapsed_sec and r.created_at <= e.created_at:
                extra = max(extra, (r.created_at - start).total_seconds() - r.elapsed_sec)
        goals.append({'eventId': e.event_id, 'elapsedSec': e.elapsed_sec,
                      'videoSec': round(offset + e.elapsed_sec + extra, 3)})
    if not goals:
        raise BadRequest('시각이 기록된 유효한 골이 없습니다.', 'VIDEO_NO_GOALS')
    if len(goals) > 100:
        raise BadRequest('한 영상은 골 100개까지 분석할 수 있습니다.')
    return goals


def run(args, timeout=180):
    return subprocess.run(args, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=timeout).stdout


def probe(path):
    raw = run(['ffprobe', '-v', 'error', '-protocol_whitelist', 'file,pipe', '-format_whitelist', 'mov,matroska,webm,avi,mpegts', '-show_format', '-show_streams', '-of', 'json', str(path)], 30)
    info = json.loads(raw)
    duration = float(info['format']['duration'])
    streams = [s for s in info['streams'] if s['codec_type'] == 'video']
    if not streams or not math.isfinite(duration) or not 0 < duration <= 14400:
        raise ValueError('duration')
    s = streams[0]
    if s.get('width', 0) * s.get('height', 0) > 3840 * 2160:
        raise ValueError('resolution')
    return duration


def motion_candidates(raw, start):
    size = 160 * 90
    scores = []
    previous = None
    for i in range(len(raw) // size):
        frame = raw[i * size:(i + 1) * size]
        if previous is not None:
            score = sum(abs(a - b) for a, b in zip(frame, previous)) / size
            if score >= 1:
                scores.append((score, start + i / 2))
        previous = frame
    picked = []
    for score, at in sorted(scores, reverse=True):
        if all(abs(at - p['videoSec']) >= 5 for p in picked):
            picked.append({'videoSec': round(at, 2), 'motion': round(score, 2)})
        if len(picked) == 3:
            break
    return sorted(picked, key=lambda p: p['videoSec'])


def process(video_id):
    with PROCESS_LOCK, SessionLocal() as db:
        v = db.get(MatchVideo, video_id)
        if not v or v.status != 'PROCESSING':
            return
        directory = folder(v.storage_key)
        source = directory / 'source'
        try:
            duration = probe(source)
            results = []
            for goal in v.data['goals']:
                center = goal['videoSec']
                if center < 0 or center >= duration:
                    results.append({**goal, 'skipped': '골 시점이 영상 범위 밖입니다.'})
                    continue
                start, end = max(0, center - 30), min(duration, center + 30)
                clip = directory / f"{goal['eventId']}.mp4"
                common = ['ffmpeg', '-nostdin', '-v', 'error', '-threads', '1', '-protocol_whitelist', 'file,pipe', '-format_whitelist', 'mov,matroska,webm,avi,mpegts',
                          '-ss', str(start), '-i', str(source), '-t', str(end - start)]
                run(common + ['-map', '0:v:0', '-map', '0:a:0?', '-vf', r'scale=trunc(min(1280\,iw)/2)*2:-2',
                              '-c:v', 'libx264', '-threads', '1', '-preset', 'veryfast', '-crf', '25',
                              '-c:a', 'aac', '-movflags', '+faststart', '-y', str(clip)])
                raw = run(['ffmpeg', '-nostdin', '-v', 'error', '-threads', '1', '-i', str(clip),
                           '-vf', 'fps=2,scale=160:90', '-an', '-pix_fmt', 'gray', '-f', 'rawvideo', 'pipe:1'])
                results.append({**goal, 'startSec': start, 'endSec': end,
                                'candidates': motion_candidates(raw, start)})
            v.data = {**v.data, 'durationSec': duration, 'clips': results}
            v.status = 'READY'
        except Exception:
            v.status = 'FAILED'
            v.data = {**v.data, 'error': '영상 분석에 실패했습니다. 파일 형식·길이(4시간 이하)·해상도(4K 이하)를 확인하고 다시 업로드하세요.'}
            for clip in directory.glob('*.mp4'):
                clip.unlink(missing_ok=True)
        finally:
            # 저장 공간 절약: 분석 후 원본은 남기지 않는다.
            source.unlink(missing_ok=True)
        db.commit()


def view(v):
    return {'videoId': v.video_id, 'status': v.status, **v.data}


def recover_interrupted():
    """단일 worker 시작 시 이전 프로세스에서 중단된 작업을 종료 처리."""
    with SessionLocal() as db:
        for v in db.scalars(select(MatchVideo).where(MatchVideo.status == 'PROCESSING')):
            v.status = 'FAILED'
            v.data = {**v.data, 'error': '서버 재시작으로 분석이 중단됐습니다. 다시 업로드해 주세요.'}
            shutil.rmtree(folder(v.storage_key), ignore_errors=True)
        db.commit()
