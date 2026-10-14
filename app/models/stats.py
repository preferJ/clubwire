from datetime import date, datetime

from sqlalchemy import Date, ForeignKey, Integer
from sqlalchemy.orm import Mapped, mapped_column

from app.core.timeutil import utcnow
from app.models.base import Base, UtcDateTime


class MemberStatSummary(Base):
    """개인 통계 집계(파생). 원본은 MATCH_GAME/MATCH_MEMBER/MATCH_EVENT/MEMBER_TITLE. 언제든 재구성 가능."""

    __tablename__ = "MEMBER_STAT_SUMMARY"

    member_id: Mapped[int] = mapped_column("MEMBER_ID", ForeignKey("MEMBER.MEMBER_ID"), primary_key=True)
    club_id: Mapped[int] = mapped_column("CLUB_ID", ForeignKey("CLUB.CLUB_ID"), nullable=False, index=True)
    games: Mapped[int] = mapped_column("GAMES", Integer, nullable=False, default=0)
    wins: Mapped[int] = mapped_column("WINS", Integer, nullable=False, default=0)
    draws: Mapped[int] = mapped_column("DRAWS", Integer, nullable=False, default=0)
    losses: Mapped[int] = mapped_column("LOSSES", Integer, nullable=False, default=0)
    goals: Mapped[int] = mapped_column("GOALS", Integer, nullable=False, default=0)
    assists: Mapped[int] = mapped_column("ASSISTS", Integer, nullable=False, default=0)
    own_goals: Mapped[int] = mapped_column("OWN_GOALS", Integer, nullable=False, default=0)
    mvp_count: Mapped[int] = mapped_column("MVP_COUNT", Integer, nullable=False, default=0)
    title_count: Mapped[int] = mapped_column("TITLE_COUNT", Integer, nullable=False, default=0)
    sessions_attended: Mapped[int] = mapped_column("SESSIONS_ATTENDED", Integer, nullable=False, default=0)
    last_played_date: Mapped[date | None] = mapped_column("LAST_PLAYED_DATE", Date)
    updated_at: Mapped[datetime] = mapped_column(
        "UPDATED_AT", UtcDateTime, nullable=False, default=utcnow, onupdate=utcnow
    )


class MemberPairStat(Base):
    """두 선수 관계 집계(파생). PK=(MEMBER_ID_LOW, MEMBER_ID_HIGH)로 순서 중복 방지.

    CO_ATTENDANCE_COUNT  : 둘 다 확정 경기에 뛴 세션 수(기회)
    SAME_TEAM_COUNT      : 그중 같은 세션 팀이었던 세션 수
    SAME_TEAM_MATCH_COUNT: 같은 편으로 뛴 확정 경기 수(같이 뛸 때 승률의 분모)
    OPPONENT_MATCH_COUNT : 실제로 맞붙은 확정 경기 수(MATCH_MEMBER 기준. 3팀일 때 대기팀은 상대 아님)
    """

    __tablename__ = "MEMBER_PAIR_STAT"

    member_id_low: Mapped[int] = mapped_column("MEMBER_ID_LOW", ForeignKey("MEMBER.MEMBER_ID"), primary_key=True)
    member_id_high: Mapped[int] = mapped_column(
        "MEMBER_ID_HIGH", ForeignKey("MEMBER.MEMBER_ID"), primary_key=True, index=True
    )
    club_id: Mapped[int] = mapped_column("CLUB_ID", ForeignKey("CLUB.CLUB_ID"), nullable=False, index=True)
    co_attendance_count: Mapped[int] = mapped_column("CO_ATTENDANCE_COUNT", Integer, nullable=False, default=0)
    same_team_count: Mapped[int] = mapped_column("SAME_TEAM_COUNT", Integer, nullable=False, default=0)
    co_attendance_since_same_team: Mapped[int] = mapped_column(
        "CO_ATTENDANCE_SINCE_SAME_TEAM", Integer, nullable=False, default=0
    )
    same_team_match_count: Mapped[int] = mapped_column("SAME_TEAM_MATCH_COUNT", Integer, nullable=False, default=0)
    same_team_win_count: Mapped[int] = mapped_column("SAME_TEAM_WIN_COUNT", Integer, nullable=False, default=0)
    same_team_draw_count: Mapped[int] = mapped_column("SAME_TEAM_DRAW_COUNT", Integer, nullable=False, default=0)
    opponent_match_count: Mapped[int] = mapped_column("OPPONENT_MATCH_COUNT", Integer, nullable=False, default=0)
    opponent_low_win_count: Mapped[int] = mapped_column("OPPONENT_LOW_WIN_COUNT", Integer, nullable=False, default=0)
    opponent_high_win_count: Mapped[int] = mapped_column("OPPONENT_HIGH_WIN_COUNT", Integer, nullable=False, default=0)
    last_same_team_at: Mapped[date | None] = mapped_column("LAST_SAME_TEAM_AT", Date)
    last_opponent_at: Mapped[date | None] = mapped_column("LAST_OPPONENT_AT", Date)
    updated_at: Mapped[datetime] = mapped_column(
        "UPDATED_AT", UtcDateTime, nullable=False, default=utcnow, onupdate=utcnow
    )
