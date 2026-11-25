from sqlalchemy import ForeignKey, JSON, String
from sqlalchemy.orm import Mapped, mapped_column
from app.models.base import Base, Id, TimestampMixin


class MatchVideo(TimestampMixin, Base):
    __tablename__ = 'MATCH_VIDEO'
    video_id: Mapped[int] = mapped_column('VIDEO_ID', Id, primary_key=True, autoincrement=True)
    match_id: Mapped[int] = mapped_column('MATCH_ID', ForeignKey('MATCH_GAME.MATCH_ID'), index=True)
    storage_key: Mapped[str] = mapped_column('STORAGE_KEY', String(32), unique=True)
    status: Mapped[str] = mapped_column('STATUS', String(20))
    data: Mapped[dict] = mapped_column('DATA', JSON)
