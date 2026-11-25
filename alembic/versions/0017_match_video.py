"""경기 영상과 골 후보 구간."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import mysql
revision = '0017'
down_revision = '0016'
branch_labels = depends_on = None


def upgrade():
    op.create_table('MATCH_VIDEO',
        sa.Column('VIDEO_ID', sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column('MATCH_ID', sa.BigInteger(), sa.ForeignKey('MATCH_GAME.MATCH_ID'), nullable=False),
        sa.Column('STORAGE_KEY', sa.String(32), nullable=False, unique=True),
        sa.Column('STATUS', sa.String(20), nullable=False),
        sa.Column('DATA', sa.JSON(), nullable=False),
        sa.Column('CREATED_AT', mysql.DATETIME(fsp=3), nullable=False),
        sa.Column('UPDATED_AT', mysql.DATETIME(fsp=3), nullable=False))
    op.create_index('IX_MATCH_VIDEO_MATCH_ID', 'MATCH_VIDEO', ['MATCH_ID'])


def downgrade():
    op.drop_table('MATCH_VIDEO')
