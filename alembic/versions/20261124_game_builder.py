"""Teacher-owned games and immutable lesson publication snapshots."""
from alembic import op
import sqlalchemy as sa
revision='wemath_games_20261124'
down_revision='wemath_teams_media_20261124'
branch_labels=None
depends_on=None


def upgrade():
    op.create_table('teacher_games',
        sa.Column('id',sa.Integer(),primary_key=True),
        sa.Column('teacher_id',sa.Integer(),sa.ForeignKey('users.id'),nullable=False),
        sa.Column('title',sa.String(180),nullable=False),sa.Column('grade',sa.Integer(),nullable=False),
        sa.Column('book_id',sa.Text(),nullable=True),sa.Column('unit_id',sa.Text(),nullable=True),sa.Column('lesson_id',sa.Text(),nullable=True),
        sa.Column('game',sa.JSON(),nullable=False),sa.Column('external_url',sa.String(2000),nullable=False),
        sa.Column('status',sa.String(20),nullable=False),sa.Column('version',sa.Integer(),nullable=False),
        sa.Column('published_lesson_id',sa.Text(),sa.ForeignKey('wemath_curriculum.lessons.id'),nullable=True),
        sa.Column('published_payload',sa.JSON(),nullable=True),
        sa.Column('updated_at',sa.DateTime(timezone=True),server_default=sa.func.now(),nullable=False))
    for key in ('teacher_id','status','published_lesson_id'):op.create_index('ix_teacher_games_'+key,'teacher_games',[key])


def downgrade():
    op.drop_table('teacher_games')
