"""member birth year

선수 프로필 정보: 출생연도 추가(가입일 JOINED_AT은 이미 있음).
- MEMBER.BIRTH_YEAR 추가(SMALLINT, NULL 허용). 관리자가 선수 화면에서 입력, 프로필에 'n년생'으로 표시
- 기존 데이터는 NULL이라 동작 변화 없음

Revision ID: 0005
Revises: 0004
Create Date: 2026-10-23 10:00:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '0005'
down_revision: Union[str, None] = '0004'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('MEMBER', sa.Column('BIRTH_YEAR', sa.SmallInteger(), nullable=True,
                                      comment="출생연도(예: 1992). 선수 프로필에 'n년생'으로 표시"))


def downgrade() -> None:
    op.drop_column('MEMBER', 'BIRTH_YEAR')
