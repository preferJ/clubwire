"""일정 삭제 보관함. 완료된 경기 기록과 통계는 보존한다."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import mysql

revision = "0009"
down_revision = "0008"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("SESSION", sa.Column("DELETED_AT", mysql.DATETIME(fsp=3), nullable=True,
                                      comment="일정 삭제 시각(기록 보존)"))
    op.execute("UPDATE `SESSION` SET DELETED_AT = COALESCE(CANCELLED_AT, CURRENT_TIMESTAMP(3)) WHERE STATUS = 'CANCELLED'")


def downgrade() -> None:
    op.drop_column("SESSION", "DELETED_AT")
