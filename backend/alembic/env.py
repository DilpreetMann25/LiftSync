"""Alembic environment configuration.

The only meaningful change from the generated default is where the
database URL comes from. Alembic's template reads it out of
alembic.ini -- which means the password would sit in a file that gets
committed to Git. Instead we read it from the environment (.env),
which is gitignored.

That single change is why the same migration command works unmodified
against local Docker, CI, and AWS RDS: only the env var differs.
"""

import os
from logging.config import fileConfig
from pathlib import Path

from alembic import context
from dotenv import load_dotenv
from sqlalchemy import engine_from_config, pool

# ---------------------------------------------------------------
# Load the repo-root .env. This file is backend/alembic/env.py, so
# parents[2] is the repo root -- the same .env docker compose reads,
# which means the port and password are defined in exactly one place.
# ---------------------------------------------------------------
REPO_ROOT = Path(__file__).resolve().parents[2]
load_dotenv(REPO_ROOT / ".env")

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    raise RuntimeError(
        "DATABASE_URL is not set. Copy .env.example to backend/.env and fill it in."
    )

# Override whatever alembic.ini says. escape '%' because ConfigParser
# treats it as interpolation syntax -- passwords containing % would
# otherwise blow up here with a confusing error.
config.set_main_option("sqlalchemy.url", DATABASE_URL.replace("%", "%%"))

# No SQLAlchemy models yet -- migrations are hand-written SQL for now.
# In Phase 2 this becomes Base.metadata and unlocks `alembic revision
# --autogenerate`, which diffs your models against the live database.
target_metadata = None


def run_migrations_offline() -> None:
    """Generate SQL to stdout instead of touching a database.

    `alembic upgrade head --sql` uses this. Useful when a DBA has to
    review changes before they run against production.
    """
    context.configure(
        url=config.get_main_option("sqlalchemy.url"),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Connect to the database and apply migrations."""
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)

        # Everything inside runs in ONE transaction. If migration 0002
        # fails, 0001 is rolled back too -- you never end up halfway.
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
