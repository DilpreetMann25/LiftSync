"""reference data: muscle groups and exercises

Revision ID: 0002
Revises: 0001
Create Date: 2026-07-25

`down_revision = "0001"` is the link that puts this second. Alembic
never guesses order from filenames -- it follows these pointers.
"""

from pathlib import Path

from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None

SQL_DIR = Path(__file__).parent / "sql"


def upgrade() -> None:
    op.execute((SQL_DIR / "0002_reference_data.sql").read_text())


def downgrade() -> None:
    """Remove only the global reference rows.

    Scoped to created_by_user_id IS NULL so a rollback never touches a
    user's custom exercises. exercise_muscle_groups clears itself via
    ON DELETE CASCADE when its exercise goes.

    This will fail if any workout_exercises row references a global
    exercise -- ON DELETE RESTRICT doing its job. That failure is
    correct: you should not be able to silently delete movements
    somebody has already logged.
    """
    op.execute("DELETE FROM exercises WHERE created_by_user_id IS NULL;")
    op.execute("DELETE FROM muscle_groups;")
