"""more titles

이달의 득점왕 · 도움왕(월 마감) + 연속 참가 10 · 20 · 30 · 40 · 50회([일정마감], 참석 명단 기준).
테이블 구조는 그대로, 컬럼 설명(COMMENT)만 바꾼다. 타이틀 정의 행(MONTHLY_TOP_SCORER / MONTHLY_TOP_ASSIST /
ATTEND_STREAK_10~50)은 새 클럽은 생성 때, 기존 클럽은 처음 필요할 때 앱이 만든다(샘플 SQL을 다시 넣어도 동작).

Revision ID: 0008
Revises: 0007
Create Date: 2026-10-23 18:00:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '0008'
down_revision: Union[str, None] = '0007'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table_comment('TITLE_TYPE', '타이틀 정의(이주의 · 이달의 득점왕/도움왕, 이달의 MVP, 연속 참가 n회 …)', existing_comment='타이틀 정의(이주의 득점왕/도움왕, 이달의 MVP …)')
    op.alter_column('TITLE_TYPE', 'AUTO_RULE', existing_type=sa.String(length=30), existing_nullable=True,
                    comment='자동 규칙: TOP_GOALS/TOP_ASSISTS/TOP_WINS, MONTHLY_RATING_RISE(이달의 MVP), ATTENDANCE_STREAK(연속 참가, 코드 끝 숫자 = 횟수)', existing_comment='자동 규칙: TOP_GOALS/TOP_ASSISTS/TOP_WINS, MONTHLY_RATING_RISE(이달의 MVP 전용)')


def downgrade() -> None:
    op.create_table_comment('TITLE_TYPE', '타이틀 정의(이주의 득점왕/도움왕, 이달의 MVP …)', existing_comment='타이틀 정의(이주의 · 이달의 득점왕/도움왕, 이달의 MVP, 연속 참가 n회 …)')
    op.alter_column('TITLE_TYPE', 'AUTO_RULE', existing_type=sa.String(length=30), existing_nullable=True,
                    comment='자동 규칙: TOP_GOALS/TOP_ASSISTS/TOP_WINS, MONTHLY_RATING_RISE(이달의 MVP 전용)', existing_comment='자동 규칙: TOP_GOALS/TOP_ASSISTS/TOP_WINS, MONTHLY_RATING_RISE(이달의 MVP), ATTENDANCE_STREAK(연속 참가, 코드 끝 숫자 = 횟수)')
