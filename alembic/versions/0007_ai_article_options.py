"""ai article options

AI 기사 설정(창의성 AI_TEMPERATURE, 답변 최대 길이 AI_MAX_OUTPUT_TOKENS)은 SYSTEM_CONFIG 값이라 구조 변경 없음
(없으면 기본값 0.7 / 2000). AI로 못 쓰면 기본형 기사(템플릿)로 대신 쓰는 것에 맞춰 컬럼 설명(COMMENT)만 바꾼다.

Revision ID: 0007
Revises: 0006
Create Date: 2026-10-23 15:00:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '0007'
down_revision: Union[str, None] = '0006'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

OLD_MODEL, NEW_MODEL = '사용 모델(stub=개발용)', '사용 모델. template = 기본형 기사(AI 키 없음 · AI 실패), sample-template = 샘플 데이터'
OLD_ERR, NEW_ERR = '실패 사유', "실패 사유 또는 기본형으로 쓴 이유('기본형으로 작성: …')"


def upgrade() -> None:
    op.alter_column('AI_ARTICLE', 'MODEL_NAME', existing_type=sa.String(length=100), existing_nullable=False,
                    comment=NEW_MODEL, existing_comment=OLD_MODEL)
    op.alter_column('AI_ARTICLE', 'ERROR_MESSAGE', existing_type=sa.Text(), existing_nullable=True,
                    comment=NEW_ERR, existing_comment=OLD_ERR)


def downgrade() -> None:
    op.alter_column('AI_ARTICLE', 'MODEL_NAME', existing_type=sa.String(length=100), existing_nullable=False,
                    comment=OLD_MODEL, existing_comment=NEW_MODEL)
    op.alter_column('AI_ARTICLE', 'ERROR_MESSAGE', existing_type=sa.Text(), existing_nullable=True,
                    comment=OLD_ERR, existing_comment=NEW_ERR)
