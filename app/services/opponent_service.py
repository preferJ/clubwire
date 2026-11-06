"""원정팀 목록(클럽별). 원정 경기의 상대는 이 목록에서만 고르고, 목록에 없으면 같은 화면의 [직접추가]로 등록한다.

이름 비교는 공백 · 대소문자를 무시한다('한강FC'와 ' 한강 fc'는 같은 팀) → 같은 상대 전적이 둘로 갈리지 않게.
관리자 [원정팀 관리]: 이름 수정(지난 원정 일정 표시도 새 이름으로) · 숨기기(목록에서만 빠지고 지난 전적은 유지) · 복원.
"""
from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from app.core.database import emit
from app.core.errors import BadRequest, Conflict, NotFound
from app.models import ClubSession, OpponentTeam, SessionTeam
from app.services.history import opponent_key


def list_opponents(db: Session, club_id: int, include_hidden: bool = False) -> list[OpponentTeam]:
    stmt = select(OpponentTeam).where(OpponentTeam.club_id == club_id)
    if not include_hidden:
        stmt = stmt.where(OpponentTeam.active_yn.is_(True))
    return list(db.scalars(stmt.order_by(OpponentTeam.active_yn.desc(), OpponentTeam.name)))


def get_opponent(db: Session, club_id: int, opponent_id: int | None) -> OpponentTeam:
    o = db.scalar(select(OpponentTeam).where(OpponentTeam.opponent_id == opponent_id, OpponentTeam.club_id == club_id,
                                             OpponentTeam.active_yn.is_(True))) if opponent_id else None
    if not o:
        raise NotFound("원정팀 목록에서 상대를 고르세요.", "OPPONENT_NOT_FOUND")
    return o


def _clean(name: str | None) -> str:
    clean = " ".join((name or "").split())
    if not clean:
        raise BadRequest("원정팀 이름을 입력하세요.", "OPPONENT_NAME_REQUIRED")
    if len(clean) > 50:
        raise BadRequest("원정팀 이름은 50자 이내로 입력하세요.", "OPPONENT_NAME_TOO_LONG")
    return clean


def create_opponent(db: Session, club_id: int, name: str) -> tuple[OpponentTeam, bool]:
    """[직접추가]. 이미 같은 이름(공백 · 대소문자 무시)이 있으면 새로 만들지 않고 그 팀을 돌려준다(숨긴 팀이면 다시 보이게).
    반환: (원정팀, 새로 만듦)."""
    clean = _clean(name)
    key = opponent_key(clean)
    for o in db.scalars(select(OpponentTeam).where(OpponentTeam.club_id == club_id)):
        if opponent_key(o.name) == key:
            if not o.active_yn:
                o.active_yn = True
                db.commit()
            return o, False
    o = OpponentTeam(club_id=club_id, name=clean, active_yn=True)
    db.add(o)
    db.flush()
    emit(db, club_id, "OPPONENTS_UPDATED", {"opponentId": o.opponent_id})
    db.commit()
    return o, True


def update_opponent(db: Session, club_id: int, opponent_id: int, *, name: str | None = None,
                    active: bool | None = None) -> OpponentTeam:
    """[원정팀 관리] 이름 수정 · 숨기기(active=False) · 복원(active=True).
    이름을 바꾸면 이 팀과의 지난 원정 일정 · 경기 화면 표시도 새 이름으로 맞춘다(이미 쓴 기사는 그대로)."""
    o = db.scalar(select(OpponentTeam).where(OpponentTeam.opponent_id == opponent_id, OpponentTeam.club_id == club_id)
                  .with_for_update())
    if not o:
        raise NotFound("원정팀을 찾을 수 없습니다.", "OPPONENT_NOT_FOUND")
    if name is not None:
        clean = _clean(name)
        key = opponent_key(clean)
        for other in db.scalars(select(OpponentTeam).where(OpponentTeam.club_id == club_id,
                                                           OpponentTeam.opponent_id != opponent_id)):
            if opponent_key(other.name) == key:
                raise Conflict(f"같은 이름의 원정팀({other.name})이 이미 있어요{'(숨긴 팀)' if not other.active_yn else ''}.",
                               "OPPONENT_EXISTS")
        if clean != o.name:
            o.name = clean
            sids = select(ClubSession.session_id).where(ClubSession.club_id == club_id,
                                                         ClubSession.opponent_id == opponent_id)
            db.execute(update(ClubSession).where(ClubSession.club_id == club_id, ClubSession.opponent_id == opponent_id)
                       .values(opponent_name=clean))
            db.execute(update(SessionTeam).where(SessionTeam.session_id.in_(sids), SessionTeam.opponent_yn.is_(True))
                       .values(display_name=clean))
    if active is not None:
        o.active_yn = active
    db.flush()
    emit(db, club_id, "OPPONENTS_UPDATED", {"opponentId": o.opponent_id})
    db.commit()
    return o


def session_counts(db: Session, club_id: int) -> dict[int, int]:
    """원정팀별 원정 일정 수(삭제한 일정 제외) — 관리 화면 안내용."""
    return dict(db.execute(select(ClubSession.opponent_id, func.count()).where(
        ClubSession.club_id == club_id, ClubSession.away_yn.is_(True), ClubSession.deleted_at.is_(None),
        ClubSession.opponent_id.is_not(None)).group_by(ClubSession.opponent_id)).all())


def serialize_opponent(o: OpponentTeam, sessions: int | None = None) -> dict:
    data = {"opponentId": o.opponent_id, "name": o.name, "active": o.active_yn}
    if sessions is not None:
        data["sessions"] = sessions
    return data


__all__ = ["list_opponents", "get_opponent", "create_opponent", "update_opponent", "session_counts",
           "serialize_opponent"]
