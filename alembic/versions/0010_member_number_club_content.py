"""선수 등번호, 클럽별 운영수칙과 상단 공지. 기존 데이터는 그대로 유지한다."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import mysql

revision = "0010"
down_revision = "0009"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("MEMBER", sa.Column("JERSEY_NUMBER", sa.SmallInteger(), nullable=True,
                                     comment="등번호(0~99). 미지정이면 NULL"))
    op.add_column("CLUB", sa.Column("OPERATING_RULES", mysql.MEDIUMTEXT(), nullable=True,
                                   comment="클럽 운영수칙. NULL이면 기존 YPR 원문 사용"))
    op.add_column("CLUB", sa.Column("OPERATING_RULES_UPDATED_AT", mysql.DATETIME(fsp=3), nullable=True,
                                   comment="운영수칙 수정 시각(UTC)"))
    op.add_column("CLUB", sa.Column("ANNOUNCEMENT", sa.String(500), nullable=True,
                                   comment="와이어 상단 한 줄 공지. NULL 또는 빈 값이면 숨김"))
    op.add_column("CLUB", sa.Column("ANNOUNCEMENT_UPDATED_AT", mysql.DATETIME(fsp=3), nullable=True,
                                   comment="상단 공지 수정 시각(UTC)"))


def downgrade() -> None:
    op.drop_column("CLUB", "ANNOUNCEMENT_UPDATED_AT")
    op.drop_column("CLUB", "ANNOUNCEMENT")
    op.drop_column("CLUB", "OPERATING_RULES_UPDATED_AT")
    op.drop_column("CLUB", "OPERATING_RULES")
    op.drop_column("MEMBER", "JERSEY_NUMBER")
