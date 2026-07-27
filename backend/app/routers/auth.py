"""Registration, login, and the current-user endpoint."""

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy import text
from sqlalchemy.engine import Connection

from app.db import get_connection
from app.dependencies import get_current_user
from app.schemas import Token, UserIn, UserOut
from app.security import create_access_token, hash_password, verify_password

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])


@router.post("/register", response_model=UserOut, status_code=status.HTTP_201_CREATED)
def register(payload: UserIn, conn: Connection = Depends(get_connection)) -> dict:
    """Create an account.

    201 Created, not 200 OK -- the status code should say what
    happened. Clients and monitoring tools rely on this distinction.

    The password is hashed BEFORE it goes anywhere near the database.
    The plaintext exists only inside this function, in memory, for a
    few milliseconds.
    """
    existing = conn.execute(
        text("SELECT 1 FROM users WHERE lower(email) = lower(:email);"),
        {"email": payload.email},
    ).first()

    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="An account with that email already exists.",
        )

    row = conn.execute(
        text(
            """
            INSERT INTO users (email, password_hash, display_name, height_cm)
            VALUES (:email, :password_hash, :display_name, :height_cm)
            RETURNING id, email, display_name, height_cm;
            """
        ),
        {
            "email": payload.email,
            "password_hash": hash_password(payload.password),
            "display_name": payload.display_name,
            "height_cm": payload.height_cm,
        },
    ).mappings().one()

    # engine.connect() does not autocommit. Without this the INSERT is
    # rolled back when the connection returns to the pool, and the
    # endpoint cheerfully returns a user that does not exist.
    conn.commit()

    return dict(row)


@router.post("/login", response_model=Token)
def login(
    form_data: OAuth2PasswordRequestForm = Depends(),
    conn: Connection = Depends(get_connection),
) -> dict:
    """Exchange email + password for an access token.

    OAuth2PasswordRequestForm reads form-encoded fields named
    `username` and `password` -- not JSON. That naming is fixed by the
    OAuth2 spec, so email goes in the `username` field. Using the
    standard form is what makes the Authorize button in /docs work.
    """
    row = conn.execute(
        text(
            """
            SELECT id, password_hash
            FROM users
            WHERE lower(email) = lower(:email);
            """
        ),
        {"email": form_data.username},
    ).mappings().first()

    # ONE error message for both "no such user" and "wrong password".
    # Distinguishing them would let an attacker enumerate which email
    # addresses have accounts -- useful for targeted phishing, and a
    # real finding in security audits.
    if row is None or not verify_password(form_data.password, row["password_hash"]):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return {"access_token": create_access_token(row["id"]), "token_type": "bearer"}


@router.get("/me", response_model=UserOut)
def read_current_user(current_user: dict = Depends(get_current_user)) -> dict:
    """Who am I?

    The entire body is `return current_user`. Declaring the dependency
    is what makes this endpoint authenticated -- FastAPI rejects the
    request with 401 before this function ever runs if the token is
    missing, expired, or forged.
    """
    return current_user
