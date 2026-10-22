"""remove mvp title

MVP(이주의 MVP) 기능 제거. 테이블 구조는 그대로 두고 데이터만 바꾼다.
- 기존 클럽의 TITLE_TYPE 'MVP'를 비활성화(ACTIVE_YN=0) → 마감 화면 선정·수여 API에서 사라짐
- 지난 MVP 수여 이력(MEMBER_TITLE)은 삭제하지 않는다(화면 조회에서만 제외)
- 새 클럽은 기본 타이틀에 MVP가 없다(club_service.DEFAULT_TITLES)

Revision ID: 0004
Revises: 0003
Create Date: 2026-10-22 18:00:00.000000
"""
from typing import Sequence, Union

from alembic import op


revision: str = '0004'
down_revision: Union[str, None] = '0003'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("UPDATE `TITLE_TYPE` SET `ACTIVE_YN` = 0 WHERE `TITLE_CODE` = 'MVP'")


def downgrade() -> None:
    op.execute("UPDATE `TITLE_TYPE` SET `ACTIVE_YN` = 1 WHERE `TITLE_CODE` = 'MVP'")
