"""원정 경기: 1팀 편성 + 원정팀(상대). 원정팀은 클럽별 목록(OPPONENT_TEAM)에서만 고른다.
원정 기록은 내부 기록과 완전히 분리한다. 기존 일정은 모두 내부 경기(AWAY_YN=0)."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import mysql

revision = "0014"
down_revision = "0013"
branch_labels = None
depends_on = None

_TEAM_CODE_OLD = "팀 코드(A, B, C …)"
_TEAM_CODE_NEW = "팀 코드(A, B, C …, 원정팀은 VS)"
_DT = sa.DateTime().with_variant(mysql.DATETIME(fsp=3), "mysql")


def upgrade() -> None:
    op.create_table(
        "OPPONENT_TEAM",
        sa.Column("OPPONENT_ID", sa.BigInteger(), autoincrement=True, nullable=False, comment="원정팀 ID"),
        sa.Column("CLUB_ID", sa.BigInteger(), nullable=False, comment="클럽 ID"),
        sa.Column("NAME", sa.String(length=50), nullable=False,
                  comment="원정팀 이름(클럽 안에서 중복 불가, 공백 · 대소문자만 다른 이름도 같은 팀으로 봄)"),
        sa.Column("ACTIVE_YN", sa.Boolean(), nullable=False, comment="사용 여부(false=비활성, 삭제 대신 사용)"),
        sa.Column("UPDATED_AT", _DT, nullable=False, comment="수정 일시(UTC)"),
        sa.Column("CREATED_AT", _DT, nullable=False, comment="생성 일시(UTC)"),
        sa.ForeignKeyConstraint(["CLUB_ID"], ["CLUB.CLUB_ID"], name=op.f("FK_OPPONENT_TEAM_CLUB_ID")),
        sa.PrimaryKeyConstraint("OPPONENT_ID", name=op.f("PK_OPPONENT_TEAM")),
        sa.UniqueConstraint("CLUB_ID", "NAME", name=op.f("UQ_OPPONENT_TEAM_CLUB_ID_NAME")),
        comment="원정팀 목록(클럽별). 원정 경기의 상대는 이 목록에서만 고른다([직접추가]로 등록)",
    )
    op.add_column("SESSION", sa.Column(
        "AWAY_YN", sa.Boolean(), nullable=False, server_default=sa.text("0"),
        comment="원정 경기 일정 여부(1팀 편성 + 원정팀). 원정 기록은 개인 기록 · 실력 점수 · 타이틀 · MVP와 분리 집계"))
    op.add_column("SESSION", sa.Column("OPPONENT_ID", sa.BigInteger(), nullable=True,
                                       comment="원정팀(OPPONENT_TEAM). 원정 경기 일정만, 상대별 전적은 이 ID로 묶음"))
    op.create_foreign_key(op.f("FK_SESSION_OPPONENT_ID"), "SESSION", "OPPONENT_TEAM", ["OPPONENT_ID"], ["OPPONENT_ID"])
    op.add_column("SESSION", sa.Column("OPPONENT_NAME", sa.String(50), nullable=True,
                                       comment="원정팀 이름(표시용, 원정팀 목록 이름)"))
    op.add_column("SESSION_TEAM", sa.Column(
        "OPPONENT_YN", sa.Boolean(), nullable=False, server_default=sa.text("0"),
        comment="원정팀(상대 팀) 여부. 선수 명단 없이 점수만 기록"))
    op.alter_column("SESSION_TEAM", "TEAM_CODE", existing_type=sa.String(5), existing_nullable=False,
                    comment=_TEAM_CODE_NEW, existing_comment=_TEAM_CODE_OLD)


def downgrade() -> None:
    op.alter_column("SESSION_TEAM", "TEAM_CODE", existing_type=sa.String(5), existing_nullable=False,
                    comment=_TEAM_CODE_OLD, existing_comment=_TEAM_CODE_NEW)
    op.drop_column("SESSION_TEAM", "OPPONENT_YN")
    op.drop_column("SESSION", "OPPONENT_NAME")
    op.drop_constraint(op.f("FK_SESSION_OPPONENT_ID"), "SESSION", type_="foreignkey")
    op.drop_column("SESSION", "OPPONENT_ID")
    op.drop_column("SESSION", "AWAY_YN")
    op.drop_table("OPPONENT_TEAM")
