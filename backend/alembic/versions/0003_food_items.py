"""reference data: food items

Revision ID: 0003
Revises: 0002
Create Date: 2026-07-25

Your first migration written AFTER the initial schema -- the pattern
every future change follows. Note that 0001 and 0002 were not touched.
"""

from pathlib import Path

from alembic import op

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None

SQL_DIR = Path(__file__).parent / "sql"


def upgrade() -> None:
    op.execute((SQL_DIR / "0003_food_items.sql").read_text())


def downgrade() -> None:
    """Remove global food items only, never a user's custom entries."""
    op.execute("DELETE FROM food_items WHERE created_by_user_id IS NULL;")
