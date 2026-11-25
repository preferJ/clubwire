"""카카오 로그인 계정, 선수 연결 승인, 경기 조작자 계정 기록."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import mysql

revision = "0016"
down_revision = "0015"
branch_labels = None
depends_on = None


def timestamps():
    return [sa.Column("CREATED_AT", mysql.DATETIME(fsp=3), nullable=False),
            sa.Column("UPDATED_AT", mysql.DATETIME(fsp=3), nullable=False)]


def upgrade():
    op.create_table("APP_USER",
        sa.Column("USER_ID", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("KAKAO_ID", sa.String(40), nullable=False, unique=True),
        sa.Column("NICKNAME", sa.String(100), nullable=False),
        sa.Column("ACTIVE_YN", sa.Boolean(), nullable=False),
        sa.Column("TOKEN_VERSION", sa.Integer(), nullable=False), *timestamps())
    op.create_table("MEMBER_ACCOUNT_LINK",
        sa.Column("LINK_ID", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("CLUB_ID", sa.BigInteger(), sa.ForeignKey("CLUB.CLUB_ID"), nullable=False),
        sa.Column("USER_ID", sa.BigInteger(), sa.ForeignKey("APP_USER.USER_ID"), nullable=False),
        sa.Column("MEMBER_ID", sa.BigInteger(), sa.ForeignKey("MEMBER.MEMBER_ID"), nullable=False),
        sa.Column("APPROVED_BY_ADMIN_ID", sa.BigInteger(), sa.ForeignKey("CLUB_ADMIN.ADMIN_ID"), nullable=False),
        sa.Column("APPROVED_AT", mysql.DATETIME(fsp=3), nullable=False),
        *timestamps(), sa.UniqueConstraint("CLUB_ID", "USER_ID"), sa.UniqueConstraint("MEMBER_ID"))
    op.create_table("MEMBER_LINK_REQUEST",
        sa.Column("REQUEST_ID", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("CLUB_ID", sa.BigInteger(), sa.ForeignKey("CLUB.CLUB_ID"), nullable=False),
        sa.Column("USER_ID", sa.BigInteger(), sa.ForeignKey("APP_USER.USER_ID"), nullable=False),
        sa.Column("MEMBER_ID", sa.BigInteger(), sa.ForeignKey("MEMBER.MEMBER_ID"), nullable=False),
        sa.Column("STATUS", sa.String(12), nullable=False),
        sa.Column("REVIEWED_BY_ADMIN_ID", sa.BigInteger(), sa.ForeignKey("CLUB_ADMIN.ADMIN_ID")),
        sa.Column("REVIEWED_AT", mysql.DATETIME(fsp=3)), *timestamps())
    op.create_index("IX_MEMBER_LINK_REQUEST_CLUB_ID", "MEMBER_LINK_REQUEST", ["CLUB_ID"])
    op.create_index("IX_MEMBER_LINK_REQUEST_USER_ID", "MEMBER_LINK_REQUEST", ["USER_ID"])
    op.add_column("MATCH_EVENT", sa.Column("USER_ID", sa.BigInteger(), nullable=True))
    op.create_foreign_key("FK_MATCH_EVENT_USER_ID", "MATCH_EVENT", "APP_USER", ["USER_ID"], ["USER_ID"])


def downgrade():
    op.drop_constraint("FK_MATCH_EVENT_USER_ID", "MATCH_EVENT", type_="foreignkey")
    op.drop_column("MATCH_EVENT", "USER_ID")
    op.drop_table("MEMBER_LINK_REQUEST")
    op.drop_table("MEMBER_ACCOUNT_LINK")
    op.drop_table("APP_USER")
