"""Delegated content dashboards and publication snapshots."""
from alembic import op
import sqlalchemy as sa

revision = "wemath_cms_20261119"
down_revision = "wemath_competitions_20261029"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table("cms_workspaces",
        sa.Column("id", sa.Integer(), primary_key=True), sa.Column("name", sa.String(150), nullable=False),
        sa.Column("modules", sa.JSON(), nullable=False), sa.Column("can_publish", sa.Boolean(), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False), sa.Column("version", sa.Integer(), nullable=False))
    op.create_table("cms_memberships",
        sa.Column("workspace_id", sa.Integer(), sa.ForeignKey("cms_workspaces.id"), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), primary_key=True))
    op.create_table("cms_content",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("workspace_id", sa.Integer(), sa.ForeignKey("cms_workspaces.id"), nullable=False),
        sa.Column("module", sa.String(40), nullable=False), sa.Column("title", sa.String(180), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False), sa.Column("status", sa.String(20), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("source_entry_id", sa.String(80), sa.ForeignKey("platform_entries.id"), unique=True, nullable=True),
        sa.Column("author_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False))
    for key in ("workspace_id", "module", "status"):
        op.create_index(f"ix_cms_content_{key}", "cms_content", [key])
    op.create_table("cms_lesson_resources",
        sa.Column("content_id", sa.Integer(), sa.ForeignKey("cms_content.id"), primary_key=True),
        sa.Column("lesson_id", sa.Text(), sa.ForeignKey("wemath_curriculum.lessons.id"), nullable=False),
        sa.Column("resource_type", sa.String(30), nullable=False), sa.Column("payload", sa.JSON(), nullable=False))
    op.create_index("ix_cms_lesson_resources_lesson_id", "cms_lesson_resources", ["lesson_id"])
    op.create_table("cms_audit",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("actor_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("action", sa.String(60), nullable=False), sa.Column("target", sa.String(120), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False))


def downgrade():
    for table in ("cms_audit", "cms_lesson_resources", "cms_content", "cms_memberships", "cms_workspaces"):
        op.drop_table(table)
