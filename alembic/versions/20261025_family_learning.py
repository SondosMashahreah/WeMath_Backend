"""Username accounts, five-child families and lesson progress; preserve existing users."""
from alembic import op
import sqlalchemy as sa

revision = "wemath_family_20261025"
down_revision = "wemath_catalog_20261019"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("users", sa.Column("username", sa.String(32), nullable=True))
    op.execute("UPDATE users SET username = 'user_' || CAST(id AS VARCHAR)")
    op.alter_column("users", "username", nullable=False)
    op.create_index("ix_users_username", "users", ["username"], unique=True)
    op.add_column("users", sa.Column("token_version", sa.Integer(), server_default="0", nullable=False))
    op.alter_column("users", "email", existing_type=sa.String(255), nullable=True)
    op.create_table("student_profiles",
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("grade", sa.Integer(), nullable=True),
        sa.Column("identity_number", sa.String(12)), sa.Column("school", sa.String(150)),
        sa.Column("phone", sa.String(20)), sa.Column("directorate", sa.String(150)),
        sa.CheckConstraint("grade BETWEEN 1 AND 12", name="ck_student_grade"))
    op.execute("""INSERT INTO student_profiles (user_id)
        SELECT DISTINCT ur.user_id FROM user_roles ur JOIN roles r ON r.id=ur.role_id WHERE r.name='student'""")
    op.execute("""INSERT INTO roles (name, description) VALUES ('student', 'Student user'), ('parent', 'Parent or guardian')
        ON CONFLICT (name) DO NOTHING""")
    op.create_table("parent_children",
        sa.Column("child_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("parent_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("slot", sa.Integer(), nullable=False),
        sa.UniqueConstraint("parent_id", "slot", name="uq_parent_child_slot"),
        sa.CheckConstraint("slot BETWEEN 1 AND 5", name="ck_parent_child_slot"),
        sa.CheckConstraint("parent_id <> child_id", name="ck_parent_not_child"))
    op.create_index("ix_parent_children_parent_id", "parent_children", ["parent_id"])
    op.create_table("lesson_progress",
        sa.Column("student_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("lesson_id", sa.Text(), sa.ForeignKey("wemath_curriculum.lessons.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("status", sa.String(16), nullable=False), sa.Column("last_activity", sa.String(24), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
        sa.CheckConstraint("status IN ('started', 'completed')", name="ck_progress_status"))


def downgrade():
    # Explicit rollback removes family/progress data, not users or curriculum.
    op.drop_table("lesson_progress")
    op.drop_table("parent_children")
    op.drop_table("student_profiles")
    op.drop_column("users", "token_version")
    op.drop_index("ix_users_username", table_name="users")
    op.drop_column("users", "username")
    # Keep nullable email: newly registered children may not have an email.
