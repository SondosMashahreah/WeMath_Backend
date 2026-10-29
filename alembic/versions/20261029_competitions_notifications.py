"""Competition detail metadata and email delivery audit."""
from alembic import op
import sqlalchemy as sa

revision = "wemath_competitions_20261029"
down_revision = "wemath_accounts_20261029"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("platform_entries", sa.Column("details", sa.JSON(), nullable=True))
    op.add_column("platform_entries", sa.Column("published_at", sa.DateTime(timezone=True), nullable=True))
    op.execute("UPDATE platform_entries SET published_at = NOW() WHERE published = TRUE AND published_at IS NULL")
    op.create_table(
        "platform_competition_notifications",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("entry_id", sa.String(80), sa.ForeignKey("platform_entries.id", ondelete="CASCADE"), nullable=False),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("email", sa.String(255), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="pending"),
        sa.Column("error", sa.String(500), nullable=True),
        sa.Column("attempted_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("entry_id", "user_id", name="uq_competition_notification_user"),
    )
    op.create_index("ix_platform_competition_notifications_entry_id", "platform_competition_notifications", ["entry_id"])
    op.create_index("ix_platform_competition_notifications_user_id", "platform_competition_notifications", ["user_id"])


def downgrade():
    op.drop_table("platform_competition_notifications")
    op.drop_column("platform_entries", "published_at")
    op.drop_column("platform_entries", "details")
