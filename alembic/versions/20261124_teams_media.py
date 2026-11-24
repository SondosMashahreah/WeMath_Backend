"""Team categories and persistent, publication-scoped media."""
from alembic import op
import sqlalchemy as sa
revision = 'wemath_teams_media_20261124'
down_revision = 'wemath_exam_bank_20261122'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('cms_workspaces', sa.Column('team_type', sa.String(20), nullable=False, server_default='other'))
    op.create_table('cms_staff_profiles',
        sa.Column('user_id', sa.Integer(), sa.ForeignKey('users.id'), primary_key=True),
        sa.Column('team_type', sa.String(20), nullable=False),
        sa.Column('invitation_status', sa.String(20), nullable=False))
    op.create_table('cms_media_assets',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('workspace_id', sa.Integer(), sa.ForeignKey('cms_workspaces.id'), nullable=False),
        sa.Column('module', sa.String(40), nullable=False),
        sa.Column('author_id', sa.Integer(), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('filename', sa.String(180), nullable=False),
        sa.Column('kind', sa.String(10), nullable=False),
        sa.Column('mime', sa.String(40), nullable=False),
        sa.Column('size', sa.Integer(), nullable=False),
        sa.Column('data', sa.LargeBinary(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False))
    op.create_index('ix_cms_media_assets_workspace_id', 'cms_media_assets', ['workspace_id'])
    op.create_table('cms_published_media',
        sa.Column('content_id', sa.Integer(), sa.ForeignKey('cms_content.id'), primary_key=True),
        sa.Column('asset_id', sa.String(36), sa.ForeignKey('cms_media_assets.id'), primary_key=True))


def downgrade():
    op.drop_table('cms_published_media')
    op.drop_table('cms_media_assets')
    op.drop_table('cms_staff_profiles')
    op.drop_column('cms_workspaces', 'team_type')
