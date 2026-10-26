"""Teacher workspace and remaining public sections; existing family data is preserved."""
import json
from datetime import date
from pathlib import Path

from alembic import op
import sqlalchemy as sa

revision = "wemath_platform_20261026"
down_revision = "wemath_family_20261025"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table("platform_teacher_profiles",
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("school", sa.String(150), nullable=True),
        sa.Column("session_version", sa.Integer(), nullable=False, server_default="0"))
    entries = op.create_table("platform_entries",
        sa.Column("id", sa.String(80), primary_key=True),
        sa.Column("section", sa.String(32), nullable=False),
        sa.Column("category", sa.String(32), nullable=False),
        sa.Column("title", sa.String(180), nullable=False),
        sa.Column("summary", sa.String(500), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("source_url", sa.Text(), nullable=True),
        sa.Column("event_date", sa.Date(), nullable=True),
        sa.Column("archived", sa.Boolean(), nullable=False),
        sa.Column("published", sa.Boolean(), nullable=False),
        sa.Column("is_demo", sa.Boolean(), nullable=False),
        sa.Column("activity", sa.JSON(), nullable=True))
    op.create_index("ix_platform_entries_section", "platform_entries", ["section"])
    op.create_index("ix_platform_entries_category", "platform_entries", ["category"])
    op.create_table("platform_teacher_documents",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("teacher_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("kind", sa.String(16), nullable=False),
        sa.Column("title", sa.String(180), nullable=False),
        sa.Column("grade", sa.Integer(), nullable=False),
        sa.Column("book_id", sa.Text(), sa.ForeignKey("wemath_curriculum.books.id"), nullable=True),
        sa.Column("lesson_id", sa.Text(), sa.ForeignKey("wemath_curriculum.lessons.id"), nullable=True),
        sa.Column("content", sa.JSON(), nullable=False),
        sa.Column("archived", sa.Boolean(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("grade BETWEEN 1 AND 12", name="platform_document_grade"),
        sa.CheckConstraint("kind IN ('plan','assessment')", name="platform_document_kind"),
        sa.CheckConstraint("version > 0", name="platform_document_version"))
    op.create_index("ix_platform_teacher_documents_teacher_id", "platform_teacher_documents", ["teacher_id"])
    op.execute("INSERT INTO roles (name, description) SELECT 'teacher', 'Teacher workspace' WHERE NOT EXISTS (SELECT 1 FROM roles WHERE name = 'teacher')")
    op.execute("INSERT INTO platform_teacher_profiles (user_id) SELECT ur.user_id FROM user_roles ur JOIN roles r ON r.id = ur.role_id WHERE r.name = 'teacher'")
    rows = json.loads((Path(__file__).parent.parent / "data" / "platform_catalog_20261026.json").read_text(encoding="utf-8"))
    for row in rows:
        row["event_date"] = date.fromisoformat(row["event_date"]) if row["event_date"] else None
    op.bulk_insert(entries, rows)


def downgrade():
    op.drop_table("platform_teacher_documents")
    op.drop_table("platform_entries")
    op.drop_table("platform_teacher_profiles")
    # Keep users and the teacher role: they may already be in use elsewhere.
