"""monthly mvp

이달의 MVP(그 달 실력 점수 상승률 1위, 월 마감 때 자동). 테이블 구조는 그대로, 컬럼 설명(COMMENT)만 바꾼다.
- TITLE_TYPE: PERIOD_TYPE MONTHLY, AUTO_RULE MONTHLY_RATING_RISE 추가(값은 앱 Enum)
- AI_ARTICLE: ARTICLE_TYPE MONTHLY_MVP 추가
- 'MONTHLY_MVP' 타이틀 정의 행은 새 클럽은 생성 시, 기존 클럽은 첫 월 마감 때 앱이 만든다
  (샘플 데이터 SQL을 다시 넣어도 TITLE_TYPE이 지워졌다 다시 생기므로 데이터 마이그레이션으로 넣지 않음)

Revision ID: 0006
Revises: 0005
Create Date: 2026-10-23 12:00:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '0006'
down_revision: Union[str, None] = '0005'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table_comment('TITLE_TYPE', '타이틀 정의(이주의 득점왕/도움왕, 이달의 MVP …)', existing_comment='타이틀 정의(이주의 MVP/득점왕/도움왕 …)')
    op.alter_column('TITLE_TYPE', 'PERIOD_TYPE', existing_type=sa.String(length=10), existing_nullable=False,
                    comment='WEEKLY(월~일)/SESSION/MONTHLY(1일~말일)', existing_comment='WEEKLY(월~일)/SESSION')
    op.alter_column('TITLE_TYPE', 'AWARD_METHOD', existing_type=sa.String(length=10), existing_nullable=False,
                    comment='MANUAL(관리자)/AUTO(주간: 일정마감 시, 월간: 월 마감 시 자동 집계)', existing_comment='MANUAL(관리자)/AUTO(일정마감 시 자동 집계)')
    op.alter_column('TITLE_TYPE', 'AUTO_RULE', existing_type=sa.String(length=30), existing_nullable=True,
                    comment='자동 규칙: TOP_GOALS/TOP_ASSISTS/TOP_WINS, MONTHLY_RATING_RISE(이달의 MVP 전용)', existing_comment='자동 규칙: TOP_GOALS/TOP_ASSISTS/TOP_WINS')
    op.alter_column('TITLE_TYPE', 'COUNTS_AS_MVP_YN', existing_type=sa.Boolean(), existing_nullable=False,
                    comment='MVP 횟수(MVP_COUNT) 집계 대상 여부. 이달의 MVP = 1', existing_comment='MVP 횟수 집계 대상 여부')
    op.create_table_comment('MEMBER_TITLE', '타이틀 수여 이력(이달의 MVP 포함). 비활성 타이틀의 이력은 조회 · 집계에서 제외', existing_comment='타이틀 수여 이력(MVP 이력 포함)')
    op.alter_column('MEMBER_STAT_SUMMARY', 'MVP_COUNT', existing_type=sa.Integer(), existing_nullable=False,
                    comment='이달의 MVP 수(활성 타이틀 중 COUNTS_AS_MVP_YN = 1)', existing_comment='MVP 타이틀 수')
    op.alter_column('AI_ARTICLE', 'ARTICLE_TYPE', existing_type=sa.String(length=20), existing_nullable=False,
                    comment='PRE_MATCH/SESSION_RECAP/MONTHLY_MVP(POST_MATCH 예약)', existing_comment='PRE_MATCH/SESSION_RECAP(POST_MATCH 예약)')


def downgrade() -> None:
    op.create_table_comment('TITLE_TYPE', '타이틀 정의(이주의 MVP/득점왕/도움왕 …)', existing_comment='타이틀 정의(이주의 득점왕/도움왕, 이달의 MVP …)')
    op.alter_column('TITLE_TYPE', 'PERIOD_TYPE', existing_type=sa.String(length=10), existing_nullable=False,
                    comment='WEEKLY(월~일)/SESSION', existing_comment='WEEKLY(월~일)/SESSION/MONTHLY(1일~말일)')
    op.alter_column('TITLE_TYPE', 'AWARD_METHOD', existing_type=sa.String(length=10), existing_nullable=False,
                    comment='MANUAL(관리자)/AUTO(일정마감 시 자동 집계)', existing_comment='MANUAL(관리자)/AUTO(주간: 일정마감 시, 월간: 월 마감 시 자동 집계)')
    op.alter_column('TITLE_TYPE', 'AUTO_RULE', existing_type=sa.String(length=30), existing_nullable=True,
                    comment='자동 규칙: TOP_GOALS/TOP_ASSISTS/TOP_WINS', existing_comment='자동 규칙: TOP_GOALS/TOP_ASSISTS/TOP_WINS, MONTHLY_RATING_RISE(이달의 MVP 전용)')
    op.alter_column('TITLE_TYPE', 'COUNTS_AS_MVP_YN', existing_type=sa.Boolean(), existing_nullable=False,
                    comment='MVP 횟수 집계 대상 여부', existing_comment='MVP 횟수(MVP_COUNT) 집계 대상 여부. 이달의 MVP = 1')
    op.create_table_comment('MEMBER_TITLE', '타이틀 수여 이력(MVP 이력 포함)', existing_comment='타이틀 수여 이력(이달의 MVP 포함). 비활성 타이틀의 이력은 조회 · 집계에서 제외')
    op.alter_column('MEMBER_STAT_SUMMARY', 'MVP_COUNT', existing_type=sa.Integer(), existing_nullable=False,
                    comment='MVP 타이틀 수', existing_comment='이달의 MVP 수(활성 타이틀 중 COUNTS_AS_MVP_YN = 1)')
    op.alter_column('AI_ARTICLE', 'ARTICLE_TYPE', existing_type=sa.String(length=20), existing_nullable=False,
                    comment='PRE_MATCH/SESSION_RECAP(POST_MATCH 예약)', existing_comment='PRE_MATCH/SESSION_RECAP/MONTHLY_MVP(POST_MATCH 예약)')
