"""골 수정(기존 골 취소 표시 + 고친 골 새로 기록) · 일반 회원 골 기록 · 수정 · 취소: 설명(COMMENT)만 바꾼다.

컬럼 · 데이터 변경 없음. MATCH_EVENT.ADMIN_ID는 원래 NULL 허용이라 일반 회원 기록은 NULL로 남는다.
함께 맞춘 것: 0011 · 0012에서 모델(app/models/comments.py)과 달라진 CLUB 엠블럼 컬럼 · MEMBER 테이블 설명.
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import mysql

revision = "0013"
down_revision = "0012"
branch_labels = None
depends_on = None

_TABLES = (
    # (테이블, 기존 설명, 새 설명)
    ("MATCH_EVENT", "경기 이벤트 타임라인(삭제 없음, 골 취소는 CANCELLED_YN + GOAL_CANCEL)",
     "경기 이벤트 타임라인(삭제 없음, 골 취소는 CANCELLED_YN + GOAL_CANCEL, 골 수정은 CANCELLED_YN + 새 GOAL)"),
    ("MEMBER", "클럽 구성원(경기하는 사람). 삭제 대신 ACTIVE_YN=false",
     "클럽 구성원(경기하는 사람). 쉬면 ACTIVE_YN=false, 그만두면 DELETED_AT(행은 남김)"),
)
_COLUMNS = (
    # (테이블, 컬럼, 타입, NULL 허용, 기존 설명, 새 설명)
    ("MATCH_EVENT", "REF_EVENT_ID", sa.BigInteger(), True, "취소 대상 이벤트",
     "취소 대상 골(GOAL_CANCEL) / 수정 전 골(수정으로 새로 기록한 GOAL)"),
    ("MATCH_EVENT", "CANCELLED_YN", sa.Boolean(), False, "취소된 골 여부",
     "취소되거나 수정된 골 여부(통계 · 기사에서 제외)"),
    ("MATCH_EVENT", "ADMIN_ID", sa.BigInteger(), True, "처리 관리자 ID",
     "처리 관리자 ID(NULL=관리자 모드가 아닌 일반 회원의 골 기록 · 수정 · 취소 또는 자동 처리)"),
    ("CLUB", "CREST_CONFIG", sa.JSON(), True, "클럽 엠블럼 설정. NULL이면 기존 자동 엠블럼",
     "엠블럼 설정(JSON): auto/design/image 모드, 도형·패턴·색상·문구·상징. NULL이면 기존 자동 엠블럼"),
    ("CLUB", "CREST_IMAGE", mysql.MEDIUMBLOB(), True, "검증·정규화된 PNG 엠블럼 이미지",
     "검증·정규화한 업로드 엠블럼 PNG 바이너리. 공개 API는 이미지 모드일 때만 제공"),
    ("CLUB", "DEFAULT_THEME", sa.String(10), True, "클럽 기본 테마(dark/light). NULL이면 dark",
     "클럽 기본 테마(dark/light). NULL이면 dark, 방문자가 저장한 선택이 우선"),
    ("CLUB", "APPEARANCE_UPDATED_AT", mysql.DATETIME(fsp=3), True, "클럽 엠블럼·기본 테마 변경 시각(UTC)",
     "엠블럼·기본 테마 수정 시각(UTC)"),
)


def _apply(upgrade: bool) -> None:
    for table, old, new in _TABLES:
        op.create_table_comment(table, new if upgrade else old, existing_comment=old if upgrade else new)
    for table, column, type_, nullable, old, new in _COLUMNS:
        op.alter_column(table, column, existing_type=type_, existing_nullable=nullable,
                        comment=new if upgrade else old, existing_comment=old if upgrade else new)


def upgrade() -> None:
    _apply(True)


def downgrade() -> None:
    _apply(False)
