"""클럽별 엠블럼과 기본 테마. 기존 데이터는 자동 엠블럼·다크 테마로 유지한다."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import mysql


revision = "0011"
down_revision = "0010"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("CLUB", sa.Column("CREST_CONFIG", sa.JSON(), nullable=True,
                                   comment="클럽 엠블럼 설정. NULL이면 기존 자동 엠블럼"))
    op.add_column("CLUB", sa.Column("CREST_IMAGE", sa.LargeBinary().with_variant(mysql.MEDIUMBLOB(), "mysql"),
                                   nullable=True, comment="검증·정규화된 PNG 엠블럼 이미지"))
    op.add_column("CLUB", sa.Column("DEFAULT_THEME", sa.String(10), nullable=True,
                                   comment="클럽 기본 테마(dark/light). NULL이면 dark"))
    op.add_column("CLUB", sa.Column("APPEARANCE_UPDATED_AT", mysql.DATETIME(fsp=3), nullable=True,
                                   comment="클럽 엠블럼·기본 테마 변경 시각(UTC)"))


def downgrade() -> None:
    op.drop_column("CLUB", "APPEARANCE_UPDATED_AT")
    op.drop_column("CLUB", "DEFAULT_THEME")
    op.drop_column("CLUB", "CREST_IMAGE")
    op.drop_column("CLUB", "CREST_CONFIG")
