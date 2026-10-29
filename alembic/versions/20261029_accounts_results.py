"""Student tracks and parent-visible result storage."""
from alembic import op
import sqlalchemy as sa

revision = "wemath_accounts_20261029"
down_revision = "wemath_platform_20261026"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("student_profiles", sa.Column("track", sa.String(150), nullable=True))
    op.create_table(
        "assessment_results",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("student_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("assessment_key", sa.String(120), nullable=False),
        sa.Column("title", sa.String(180), nullable=False),
        sa.Column("score", sa.Integer(), nullable=False),
        sa.Column("max_score", sa.Integer(), nullable=False),
        sa.Column("recorded_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("student_id", "assessment_key", name="uq_student_assessment_result"),
        sa.CheckConstraint("score >= 0 AND max_score > 0 AND score <= max_score", name="ck_assessment_score"),
    )
    op.create_index("ix_assessment_results_student_id", "assessment_results", ["student_id"])


def downgrade():
    op.drop_table("assessment_results")
    op.drop_column("student_profiles", "track")
