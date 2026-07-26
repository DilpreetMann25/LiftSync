"""initial schema

Revision ID: 0001
Revises:
Create Date: 2026-07-25

The first migration. `down_revision = None` marks it as the root of
the chain -- Alembic follows these links like a linked list to work
out what order to run things in.

The SQL itself lives in versions/sql/0001_initial_schema.sql rather
than inline, so it stays readable as SQL. The Python here is just the
wiring.
"""

from pathlib import Path

from alembic import op

# --- Alembic's required identifiers ---------------------------
revision = "0001"
down_revision = None
branch_labels = None
depends_on = None

SQL_DIR = Path(__file__).parent / "sql"


def upgrade() -> None:
    """Build the schema from empty."""
    op.execute((SQL_DIR / "0001_initial_schema.sql").read_text())


def downgrade() -> None:
    """Tear it all back down.

    Order matters in reverse: the view depends on the tables, and
    tables depend on the types. CASCADE would let us be sloppy, but
    writing it out explicitly means a mistake fails loudly instead of
    silently dropping something we did not intend to.
    """
    op.execute("DROP VIEW IF EXISTS v_set_details;")

    for table in (
        "ai_programs",
        "nutrition_entries",
        "food_items",
        "nutrition_logs",
        "bodyweight_logs",
        "sets",
        "workout_exercises",
        "workouts",
        "exercise_muscle_groups",
        "exercises",
        "muscle_groups",
        "users",
    ):
        op.execute(f"DROP TABLE IF EXISTS {table};")

    # The trigger function outlives its triggers (they were dropped
    # along with their tables), so it needs removing separately.
    op.execute("DROP FUNCTION IF EXISTS set_updated_at();")

    for enum in ("body_region", "exercise_category", "unit_preference"):
        op.execute(f"DROP TYPE IF EXISTS {enum};")
