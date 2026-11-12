"""일정별 공지(SESSION.NOTICE) + 상단 공지 스타일(CLUB.ANNOUNCEMENT_STYLE). 기존 데이터는 그대로(둘 다 NULL = 없음 · 기본)."""
from alembic import op
import sqlalchemy as sa


revision = "0015"
down_revision = "0014"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("SESSION", sa.Column("NOTICE", sa.String(500), nullable=True,
                                      comment="일정별 공지(최대 500자, 줄바꿈 허용). 일정 화면·메인 팀 편성 카드에서 팀 밸런스 안내 위에 표시. NULL=없음"))
    op.add_column("CLUB", sa.Column("ANNOUNCEMENT_STYLE", sa.String(10), nullable=True,
                                   comment="상단 공지 스타일(default/highlight/accent/alert, 색·배경·글자 강조·흐름 효과). NULL이면 default"))


def downgrade() -> None:
    op.drop_column("CLUB", "ANNOUNCEMENT_STYLE")
    op.drop_column("SESSION", "NOTICE")
