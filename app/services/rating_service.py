"""Rating 계산/재생(Replay).

원칙
- PLAYER_RATING / PLAYER_RATING_HISTORY는 파생 데이터. 원본(확정 경기)에서 언제든 재계산 가능.
- 경기 순서 = (SESSION_DATE, SESSION_ID, GAME_NO). 이 순서대로 Rating을 누적한다.
- 과거 경기가 바뀌면(확정/확정취소) 그 경기부터 이후 경기의 이력을 VOIDED 처리하고 다시 쌓는다.
  기존 이력은 삭제하지 않는다(감사 목적).
"""
from dataclasses import dataclass
from datetime import date

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.core.club_config import ClubConfig
from app.core.timeutil import utcnow
from app.models import ClubSession, MatchGame, MatchMember, Member, PlayerRating, PlayerRatingHistory, SessionGuest
from app.models.enums import GameStatus, RatingChangeReason, ReferenceType, SessionStatus
from app.services.common import lock_club
from app.services.config_service import load_config
from app.strategies.rating import RatedPlayer, confidence_strategy, match_rating_strategy

MatchKey = tuple[date, int, int]


@dataclass
class RatingState:
    rating: float
    match_count: int
    last_played_date: date | None


def initial_rating_of(member: Member, cfg: ClubConfig) -> float:
    """멤버의 시작 Rating: MEMBER.INITIAL_RATING(지정 시) → 없으면 클럽 설정 INITIAL_RATING."""
    return float(member.initial_rating) if member.initial_rating is not None else float(cfg["INITIAL_RATING"])


def initial_ratings(db: Session, club_id: int, cfg: ClubConfig, member_ids: list[int] | None = None) -> dict[int, float]:
    """member_id → 시작 Rating. 재계산/현재값 복원의 출발점."""
    stmt = select(Member.member_id, Member.initial_rating).where(Member.club_id == club_id)
    if member_ids is not None:
        stmt = stmt.where(Member.member_id.in_(member_ids))
    init = float(cfg["INITIAL_RATING"])
    return {mid: (float(r) if r is not None else init) for mid, r in db.execute(stmt)}


def ensure_player_rating(db: Session, member: Member, cfg: ClubConfig) -> PlayerRating:
    pr = db.get(PlayerRating, member.member_id)
    if not pr:
        pr = PlayerRating(member_id=member.member_id, club_id=member.club_id,
                          current_rating=initial_rating_of(member, cfg), match_sample_count=0)
        db.add(pr)
    return pr


def current_states(db: Session, club_id: int, member_ids: list[int], cfg: ClubConfig) -> dict[int, RatingState]:
    rows = {r.member_id: r for r in db.scalars(select(PlayerRating).where(PlayerRating.member_id.in_(member_ids)))}
    missing = [mid for mid in member_ids if mid not in rows]
    base = initial_ratings(db, club_id, cfg, missing) if missing else {}
    init = float(cfg["INITIAL_RATING"])
    out = {}
    for mid in member_ids:
        r = rows.get(mid)
        out[mid] = (RatingState(r.current_rating, r.match_sample_count, r.last_played_date) if r
                    else RatingState(base.get(mid, init), 0, None))
    return out


def confidence_of(state: RatingState, as_of: date | None, cfg: ClubConfig) -> float:
    return confidence_strategy.calculate(state.match_count, state.last_played_date, as_of, cfg)


def match_key(session: ClubSession, match: MatchGame) -> MatchKey:
    return (session.session_date, session.session_id, match.game_no)


def _finalized_matches(db: Session, club_id: int) -> list[tuple[MatchGame, ClubSession]]:
    rows = db.execute(
        select(MatchGame, ClubSession)
        .join(ClubSession, ClubSession.session_id == MatchGame.session_id)
        .where(
            ClubSession.club_id == club_id,
            ClubSession.status != SessionStatus.CANCELLED,
            MatchGame.game_status == GameStatus.FINISHED,
            MatchGame.finalized_at.is_not(None),
        )
        .order_by(ClubSession.session_date, ClubSession.session_id, MatchGame.game_no)
    ).all()
    return [(r[0], r[1]) for r in rows]


def _headcount(db: Session, match: MatchGame, team_id: int, member_count: int) -> int:
    snap = match.team_a_headcount if team_id == match.team_a_id else match.team_b_headcount
    if snap is not None:
        return snap
    guests = db.scalars(
        select(SessionGuest.guest_id).where(SessionGuest.session_team_id == team_id, SessionGuest.active_yn.is_(True))
    ).all()
    return member_count + len(guests)


def rebuild_ratings(db: Session, club_id: int, from_key: MatchKey | None = None,
                    reason: RatingChangeReason = RatingChangeReason.MATCH_RESULT) -> int:
    """from_key 이후(포함) 확정 경기의 Rating을 다시 계산한다. from_key=None이면 전체.

    호출 측 트랜잭션 안에서 실행된다(commit은 호출 측). 반환: 재계산한 경기 수.
    """
    lock_club(db, club_id)
    cfg = load_config(db, club_id)
    init = float(cfg["INITIAL_RATING"])
    finalized = _finalized_matches(db, club_id)
    start = 0
    if from_key is not None:
        start = next((i for i, (m, s) in enumerate(finalized) if match_key(s, m) >= from_key), len(finalized))
    kept_ids = [m.match_id for m, _ in finalized[:start]]

    # 1) 유지 구간 밖의 MATCH 이력 무효화(확정 취소된 경기 포함)
    void_stmt = (
        update(PlayerRatingHistory)
        .where(
            PlayerRatingHistory.club_id == club_id,
            PlayerRatingHistory.voided_yn.is_(False),
            PlayerRatingHistory.reference_type == ReferenceType.MATCH,
        )
        .values(voided_yn=True, voided_at=utcnow())
    )
    if kept_ids:
        void_stmt = void_stmt.where(PlayerRatingHistory.reference_id.not_in(kept_ids))
    db.execute(void_stmt)

    # 2) 유지 구간 끝 시점의 상태 복원(출발점은 멤버별 시작 Rating)
    base = initial_ratings(db, club_id, cfg)
    state: dict[int, RatingState] = {mid: RatingState(r, 0, None) for mid, r in base.items()}
    if kept_ids:
        order = {mid: i for i, mid in enumerate(kept_ids)}
        hist = db.scalars(
            select(PlayerRatingHistory).where(
                PlayerRatingHistory.club_id == club_id,
                PlayerRatingHistory.voided_yn.is_(False),
                PlayerRatingHistory.reference_type == ReferenceType.MATCH,
                PlayerRatingHistory.reference_id.in_(kept_ids),
            )
        ).all()
        # 경기 수/마지막 출전일도 '재생에서 실제 반영된 경기'(=유효 이력 행) 기준으로 복원한다.
        # (한쪽 팀이 비어 재생에서 건너뛴 경기는 이력이 없으므로 세지 않는다 → 전체 재계산과 동일)
        session_date_of = {m.match_id: s.session_date for m, s in finalized[:start]}
        last_idx: dict[int, int] = {}
        for h in hist:
            idx = order[h.reference_id]
            st = state.setdefault(h.member_id, RatingState(base.get(h.member_id, init), 0, None))
            st.match_count += 1
            d = session_date_of[h.reference_id]
            if st.last_played_date is None or d > st.last_played_date:
                st.last_played_date = d
            if idx >= last_idx.get(h.member_id, -1):
                last_idx[h.member_id] = idx
                st.rating = h.after_rating

    # 3) 재생
    replay = finalized[start:]
    replay_ids = [m.match_id for m, _ in replay]
    members_by_match: dict[int, list[MatchMember]] = {}
    if replay_ids:
        for mm in db.scalars(select(MatchMember).where(MatchMember.match_id.in_(replay_ids))):
            members_by_match.setdefault(mm.match_id, []).append(mm)

    strat = match_rating_strategy  # 알고리즘 교체 지점(app/strategies/rating.py)

    for m, s in replay:
        mms = members_by_match.get(m.match_id, [])
        side_a = [mm for mm in mms if mm.session_team_id == m.team_a_id]
        side_b = [mm for mm in mms if mm.session_team_id == m.team_b_id]
        if not side_a or not side_b:
            continue
        as_of = s.session_date

        def rated(mm: MatchMember) -> RatedPlayer:
            st = state.setdefault(mm.member_id, RatingState(base.get(mm.member_id, init), 0, None))
            return RatedPlayer(mm.member_id, st.rating, confidence_of(st, as_of, cfg))

        team_a = [rated(x) for x in side_a]
        team_b = [rated(x) for x in side_b]
        result = strat.calculate(
            team_a, team_b,
            _headcount(db, m, m.team_a_id, len(side_a)),
            _headcount(db, m, m.team_b_id, len(side_b)),
            m.score_a, m.score_b, cfg,
        )
        for p in team_a + team_b:
            st = state[p.member_id]
            before_conf = p.confidence
            delta = result.deltas[p.member_id]
            before = st.rating
            st.rating = before + delta
            st.match_count += 1
            st.last_played_date = as_of
            after_conf = confidence_of(st, as_of, cfg)
            db.add(
                PlayerRatingHistory(
                    club_id=club_id, member_id=p.member_id,
                    before_rating=before, after_rating=st.rating,
                    before_confidence=before_conf, after_confidence=after_conf,
                    change_amount=delta, change_reason=reason,
                    reference_type=ReferenceType.MATCH, reference_id=m.match_id,
                    algorithm_version=strat.version, config_version=cfg.version,
                    calc_detail_json={**result.detail, "multiplier": result.detail["multipliers"].get(str(p.member_id))},
                )
            )

    # 4) 현재값 갱신
    existing = {r.member_id: r for r in db.scalars(select(PlayerRating).where(PlayerRating.club_id == club_id))}
    for mid, st in state.items():
        r = existing.get(mid)
        if not r:
            db.add(PlayerRating(member_id=mid, club_id=club_id, current_rating=st.rating,
                                match_sample_count=st.match_count, last_played_date=st.last_played_date))
        else:
            r.current_rating = st.rating
            r.match_sample_count = st.match_count
            r.last_played_date = st.last_played_date
    db.flush()
    return len(replay)


def rating_rows(db: Session, club_id: int, as_of: date) -> list[dict]:
    """현재 Rating 목록. API로 내보내지 않는다(테스트·DB 점검용)."""
    cfg = load_config(db, club_id)
    rows = db.execute(
        select(Member, PlayerRating)
        .join(PlayerRating, PlayerRating.member_id == Member.member_id, isouter=True)
        .where(Member.club_id == club_id)
        .order_by(PlayerRating.current_rating.desc(), Member.name)
    ).all()
    out = []
    for m, r in rows:
        start = initial_rating_of(m, cfg)
        st = RatingState(r.current_rating, r.match_sample_count, r.last_played_date) if r else RatingState(start, 0, None)
        out.append({
            "memberId": m.member_id, "name": m.name, "active": m.active_yn,
            "initialRating": round(start, 2),
            "rating": round(st.rating, 2), "confidence": round(confidence_of(st, as_of, cfg), 4),
            "matchCount": st.match_count, "lastPlayedDate": st.last_played_date,
        })
    return out


def rating_history(db: Session, club_id: int, member_id: int, include_voided: bool = False) -> list[PlayerRatingHistory]:
    stmt = select(PlayerRatingHistory).where(
        PlayerRatingHistory.club_id == club_id, PlayerRatingHistory.member_id == member_id
    )
    if not include_voided:
        stmt = stmt.where(PlayerRatingHistory.voided_yn.is_(False))
    return list(db.scalars(stmt.order_by(PlayerRatingHistory.rating_history_id)))


__all__ = [
    "RatingState", "initial_rating_of", "initial_ratings", "ensure_player_rating", "current_states", "confidence_of", "match_key",
    "rebuild_ratings", "rating_rows", "rating_history", "match_rating_strategy",
]
