"""Reusable math questions, templates and exams, scoped to CMS workspaces."""
from alembic import op
import sqlalchemy as sa
revision = 'wemath_exam_bank_20261122'
down_revision = 'wemath_cms_20261119'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('cms_exam_bank',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('workspace_id', sa.Integer(), sa.ForeignKey('cms_workspaces.id'), nullable=False),
        sa.Column('kind', sa.String(20), nullable=False),
        sa.Column('title', sa.String(180), nullable=False),
        sa.Column('grade', sa.Integer(), nullable=True),
        sa.Column('topic', sa.String(150), nullable=False),
        sa.Column('difficulty', sa.String(20), nullable=False),
        sa.Column('payload', sa.JSON(), nullable=False),
        sa.Column('archived', sa.Boolean(), nullable=False),
        sa.Column('version', sa.Integer(), nullable=False),
        sa.Column('author_id', sa.Integer(), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False))
    op.create_index('ix_cms_exam_bank_workspace_id', 'cms_exam_bank', ['workspace_id'])


def downgrade():
    op.drop_table('cms_exam_bank')
