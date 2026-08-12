"""Shared pytest fixtures.

THE CENTRAL PROBLEM
-------------------
Tests must never touch your development database. A test that deletes
all users would wipe your demo data, and a test that depends on data
you happened to seed is a test that passes on your machine and fails
in CI.

So tests get their own database: `liftsync_test`, created on the same
Postgres server, built by the same migrations, wiped between tests.

HOW THE REDIRECTION WORKS
-------------------------
app/config.py and alembic/env.py both read DATABASE_URL from the
environment. Crucially, load_dotenv() does NOT overwrite variables
that are already set. So if we set DATABASE_URL here -- BEFORE any app
module is imported -- everything downstream points at the test
database with no code changes anywhere else.

That ordering is load-bearing. Importing app.config above these lines
would connect to your dev database instead.
"""

import os
import sys
from pathlib import Path

import pytest
from dotenv import load_dotenv\

BACKEND_DIR = Path(__file__).resolve().parents[1]
REPO_ROOT = BACKEND_DIR.parent
sys.path.insert(0, str(BACKEND_DIR))

load_dotenv(REPO_ROOT / ".env")

TEST_DB_NAME = "liftsync_test"

_dev_url = os.environ.get("DATABASE_URL")
if not _dev_url:
    raise RuntimeError("DATABASE_URL not set. Copy .env.example to .env.")

# Swap only the database name, keeping host, port, and credentials.
_base, _sep, _dev_db = _dev_url.rpartition("/")
if _dev_db == TEST_DB_NAME:
    raise RuntimeError("DATABASE_URL already points at the test database.")

TEST_DATABASE_URL = f"{_base}/{TEST_DB_NAME}"
os.environ["DATABASE_URL"] = TEST_DATABASE_URL

# Tests need a signing key but must not depend on your real one.
os.environ["JWT_SECRET_KEY"] = "test-only-signing-key-not-a-secret"
os.environ["ENVIRONMENT"] = "development"

# Only NOW is it safe to import anything from app.
import psycopg  # noqa: E402
from alembic import command  # noqa: E402
from alembic.config import Config  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import text  # noqa: E402

from app.db import engine  # noqa: E402
from app.main import app  # noqa: E402


def _create_test_database() -> None:
    """Create liftsync_test if it does not exist.

    CREATE DATABASE cannot run inside a transaction, hence autocommit.
    We connect to the built-in `postgres` database to issue it, since
    you cannot create a database from inside the one being created.
    """
    admin_url = f"{_base}/postgres".replace("+psycopg", "")
    with psycopg.connect(admin_url, autocommit=True) as conn, conn.cursor() as cur:
        cur.execute("SELECT 1 FROM pg_database WHERE datname = %s;", (TEST_DB_NAME,))
        if cur.fetchone() is None:
            # Identifier, not a value -- it cannot be parameterised.
            # Safe here because TEST_DB_NAME is a hardcoded constant,
            # never user input.
            cur.execute(f'CREATE DATABASE "{TEST_DB_NAME}";')


@pytest.fixture(scope="session", autouse=True)
def _prepare_database() -> None:
    """Create the test database and bring it up to the latest migration.

    scope="session": runs once for the whole test run, not per test.
    Running migrations before every test would be correct but slow.

    Note this exercises your migrations as a side effect. If 0003 is
    broken, the entire suite fails to start -- which is exactly the
    signal you want.
    """
    _create_test_database()

    config = Config(str(BACKEND_DIR / "alembic.ini"))
    config.set_main_option("script_location", str(BACKEND_DIR / "alembic"))
    command.upgrade(config, "head")


@pytest.fixture(autouse=True)
def _clean_tables() -> None:
    """Delete all user data before each test.

    autouse=True applies this to every test without it asking, so no
    test can accidentally depend on another's leftovers. Tests that
    share state pass in one order and fail in another, which is a
    miserable class of bug to chase.

    DELETE FROM users is enough: ON DELETE CASCADE removes workouts,
    workout_exercises, sets, nutrition and bodyweight logs. Reference
    data (created_by_user_id IS NULL) is untouched, because global rows
    reference no user.

    Deliberately NOT `TRUNCATE users CASCADE` -- that would also
    truncate `exercises`, since it has a foreign key to users, wiping
    the reference data the migrations installed.
    """
    with engine.connect() as conn:
        conn.execute(text("DELETE FROM users;"))
        conn.commit()


@pytest.fixture
def client() -> TestClient:
    """An HTTP client that calls the app in-process.

    No running uvicorn required and no real network: TestClient speaks
    to the ASGI app directly, so the suite is fast and needs nothing
    started beforehand.
    """
    return TestClient(app)


@pytest.fixture
def registered_user(client: TestClient) -> dict:
    """A freshly created account, with its credentials."""
    credentials = {
        "email": "tester@example.com",
        "password": "test-password-123",
        "display_name": "Tester",
        "height_cm": 178.0,
    }
    response = client.post("/api/v1/auth/register", json=credentials)
    assert response.status_code == 201, response.text
    return {**credentials, "id": response.json()["id"]}


@pytest.fixture
def auth_headers(client: TestClient, registered_user: dict) -> dict[str, str]:
    """Authorization header for the registered user.

    Logs in through the real endpoint rather than minting a token
    directly -- so if login breaks, these tests fail too. Bypassing it
    would hide a genuine bug.
    """
    response = client.post(
        "/api/v1/auth/login",
        # Form-encoded, and the field is `username` per the OAuth2 spec
        # even though the value is an email.
        data={
            "username": registered_user["email"],
            "password": registered_user["password"],
        },
    )
    assert response.status_code == 200, response.text
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


@pytest.fixture
def exercise_ids(client: TestClient) -> dict[str, int]:
    """Map exercise name -> id.

    Looked up rather than hardcoded. Identity sequences do not
    guarantee particular values, so a test asserting exercise 3 is the
    overhead press is a test that breaks for no good reason.
    """
    response = client.get("/api/v1/exercises")
    assert response.status_code == 200, response.text
    return {row["name"]: row["id"] for row in response.json()}
