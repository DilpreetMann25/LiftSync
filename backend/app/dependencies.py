"""Shared FastAPI dependencies.

get_current_user is the one that matters. Any endpoint that declares
it becomes authenticated -- no token, no access -- and receives the
logged-in user without doing any work itself.

That single line is what turns "show me the workouts" into "show me
MY workouts". Postgres has no idea who is logged in; this is where
that knowledge lives.
"""

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy import text
from sqlalchemy.engine import Connection

from app.db import get_connection
from app.security import decode_access_token

# Tells FastAPI where tokens come from. Two effects:
#   1. It pulls the token out of the Authorization header for you.
#   2. /docs grows an "Authorize" button wired to that login URL.
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login")


def get_current_user(
    token: str = Depends(oauth2_scheme),
    conn: Connection = Depends(get_connection),
) -> dict:
    """Resolve the bearer token into a real user row.

    Dependencies can depend on other dependencies -- this one uses
    both oauth2_scheme and get_connection, and FastAPI resolves the
    whole chain before your endpoint runs.
    """
    credentials_error = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        # Required by the HTTP spec for 401 responses; clients use it
        # to work out how they are supposed to authenticate.
        headers={"WWW-Authenticate": "Bearer"},
    )

    user_id = decode_access_token(token)
    if user_id is None:
        raise credentials_error

    # A valid signature is not enough. The token could belong to an
    # account deleted five minutes ago, so we still confirm the user
    # exists. This is the database round-trip JWTs were meant to
    # avoid -- a deliberate trade of a little speed for correctness.
    row = conn.execute(
        text(
            """
            SELECT id, email, display_name, height_cm
            FROM users
            WHERE id = :user_id;
            """
        ),
        {"user_id": user_id},
    ).mappings().first()

    if row is None:
        raise credentials_error

    return dict(row)
