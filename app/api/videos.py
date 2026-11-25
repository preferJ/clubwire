import shutil
from uuid import uuid4

from fastapi import APIRouter, BackgroundTasks, Depends, Query, Request
from fastapi.responses import FileResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import admin_dep, club_dep
from app.core.config import settings
from app.core.database import get_db
from app.core.errors import BadRequest, Conflict, NotFound
from app.models import Club, MatchVideo
from app.services.common import get_match, lock_club
from app.services import video_service as svc

router = APIRouter(tags=['match-videos'], dependencies=[Depends(admin_dep)])


@router.get('/matches/{match_id}/videos')
def listing(match_id: int, club: Club = Depends(club_dep), db: Session = Depends(get_db)):
    get_match(db, club.club_id, match_id)
    return [svc.view(v) for v in db.scalars(select(MatchVideo).where(MatchVideo.match_id == match_id).order_by(MatchVideo.video_id.desc()))]


@router.post('/matches/{match_id}/videos', status_code=202)
async def upload(match_id: int, request: Request, background: BackgroundTasks,
                 start_sec: float = Query(default=0, ge=0, le=14400, allow_inf_nan=False),
                 club: Club = Depends(club_dep), db: Session = Depends(get_db)):
    svc.require_tools()
    get_match(db, club.club_id, match_id)
    goals = svc.snapshot_goals(db, match_id, start_sec)
    # 업로드 중 다른 관리자 작업을 잠그지 않는다.
    db.rollback()
    directory = svc.folder(uuid4().hex)
    directory.mkdir(parents=True)
    limit = settings.VIDEO_MAX_MB * 1024 * 1024
    try:
        count = 0
        with (directory / 'source').open('wb') as out:
            async for chunk in request.stream():
                count += len(chunk)
                if count > limit:
                    raise BadRequest(f'영상은 {settings.VIDEO_MAX_MB}MB까지 업로드할 수 있습니다.')
                if shutil.disk_usage(directory).free < len(chunk) + 512 * 1024 * 1024:
                    raise BadRequest('서버 저장 공간이 부족합니다. 기존 영상을 삭제해 주세요.')
                out.write(chunk)
        if not count:
            raise BadRequest('영상 파일이 비어 있습니다.')
        lock_club(db, club.club_id)
        get_match(db, club.club_id, match_id)
        goals = svc.snapshot_goals(db, match_id, start_sec)
        active = db.scalar(select(MatchVideo).where(MatchVideo.match_id == match_id, MatchVideo.status == 'PROCESSING'))
        if active:
            raise Conflict('이 경기의 영상 분석이 진행 중입니다.')
        v = MatchVideo(match_id=match_id, storage_key=directory.name, status='PROCESSING',
                       data={'startSec': start_sec, 'goals': goals, 'clips': []})
        db.add(v)
        db.commit()
        background.add_task(svc.process, v.video_id)
        return svc.view(v)
    except BaseException:
        shutil.rmtree(directory, ignore_errors=True)
        raise


@router.get('/matches/{match_id}/videos/{video_id}/clips/{event_id}')
def clip(match_id: int, video_id: int, event_id: int, club: Club = Depends(club_dep), db: Session = Depends(get_db)):
    v = svc.get_video(db, club.club_id, match_id, video_id)
    if v.status != 'READY' or not any(c['eventId'] == event_id and 'skipped' not in c for c in v.data['clips']):
        raise NotFound('클립을 찾을 수 없습니다.')
    path = svc.folder(v.storage_key) / f'{event_id}.mp4'
    if not path.is_file():
        raise NotFound('클립 파일을 찾을 수 없습니다.')
    return FileResponse(path, media_type='video/mp4', headers={'Cache-Control': 'private, no-store'})


@router.delete('/matches/{match_id}/videos/{video_id}')
def remove(match_id: int, video_id: int, club: Club = Depends(club_dep), db: Session = Depends(get_db)):
    v = svc.get_video(db, club.club_id, match_id, video_id)
    if v.status == 'PROCESSING':
        raise Conflict('분석이 완료된 후 삭제할 수 있습니다.')
    key = v.storage_key
    db.delete(v)
    db.commit()
    shutil.rmtree(svc.folder(key), ignore_errors=True)
    return {'ok': True}
