"""선수 삭제(목록에서만 숨김, 행 보존) + 메인 팀 마크 크기 · 상단 공지 크기. 기존 데이터는 그대로 유지한다."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import mysql


revision = "0012"
down_revision = "0011"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("MEMBER", sa.Column("DELETED_AT", mysql.DATETIME(fsp=3), nullable=True,
                                     comment="선수 삭제 시각(UTC). NULL=정상. 목록·참석 선택·기록 순위·MVP 후보에서 숨기고 지난 기록은 보존, 복원 가능"))
    op.add_column("CLUB", sa.Column("CREST_SIZE", sa.SmallInteger(), nullable=True,
                                   comment="탭 머리(메인 화면) 팀 마크 크기(px, 32~72). NULL이면 44"))
    op.add_column("CLUB", sa.Column("ANNOUNCEMENT_SIZE", sa.String(10), nullable=True,
                                   comment="상단 공지 크기(small/medium/large, 글자·높이). NULL이면 medium"))


def downgrade() -> None:
    op.drop_column("CLUB", "ANNOUNCEMENT_SIZE")
    op.drop_column("CLUB", "CREST_SIZE")
    op.drop_column("MEMBER", "DELETED_AT")
