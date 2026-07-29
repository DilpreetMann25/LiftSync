"""Tests for registration, login, and token handling.

Each test asserts ONE behaviour. When a test fails you want its name
to tell you what broke, which is impossible if it checked six things.
"""

from fastapi.testclient import TestClient

VALID_USER = {
    "email": "newuser@example.com",
    "password": "a-good-password",
    "display_name": "New User",
}


def test_register_creates_user(client: TestClient) -> None:
    response = client.post("/api/v1/auth/register", json=VALID_USER)

    assert response.status_code == 201
    body = response.json()
    assert body["email"] == VALID_USER["email"]
    assert body["display_name"] == "New User"
    assert isinstance(body["id"], int)


def test_register_never_returns_password_fields(client: TestClient) -> None:
    """The whole reason UserIn and UserOut are separate classes.

    If someone later adds password_hash to UserOut, this fails.
    """
    response = client.post("/api/v1/auth/register", json=VALID_USER)

    body = response.json()
    assert "password" not in body
    assert "password_hash" not in body


def test_password_is_hashed_not_stored_plaintext(client: TestClient) -> None:
    """Read the database directly to prove the plaintext never lands.

    Normally tests should go through the API, but this is a security
    property the API deliberately cannot expose -- so checking it
    requires looking underneath.
    """
    from sqlalchemy import text

    from app.db import engine

    client.post("/api/v1/auth/register", json=VALID_USER)

    with engine.connect() as conn:
        stored = conn.execute(
            text("SELECT password_hash FROM users WHERE email = :email;"),
            {"email": VALID_USER["email"]},
        ).scalar_one()

    assert stored != VALID_USER["password"]
    # bcrypt hashes always start with $2b$ and encode the cost factor.
    assert stored.startswith("$2b$")


def test_register_rejects_duplicate_email(client: TestClient) -> None:
    client.post("/api/v1/auth/register", json=VALID_USER)
    response = client.post("/api/v1/auth/register", json=VALID_USER)

    assert response.status_code == 409


def test_register_rejects_duplicate_email_different_case(client: TestClient) -> None:
    """The functional index on lower(email) enforced at the API level."""
    client.post("/api/v1/auth/register", json=VALID_USER)
    response = client.post(
        "/api/v1/auth/register",
        json={**VALID_USER, "email": "NewUser@Example.COM"},
    )

    assert response.status_code == 409


def test_register_rejects_short_password(client: TestClient) -> None:
    response = client.post(
        "/api/v1/auth/register",
        json={**VALID_USER, "password": "short"},
    )

    # 422, not 400: Pydantic rejected it before the endpoint ran.
    assert response.status_code == 422


def test_register_rejects_malformed_email(client: TestClient) -> None:
    response = client.post(
        "/api/v1/auth/register",
        json={**VALID_USER, "email": "not-an-email"},
    )

    assert response.status_code == 422


def test_login_returns_bearer_token(client: TestClient, registered_user: dict) -> None:
    response = client.post(
        "/api/v1/auth/login",
        data={
            "username": registered_user["email"],
            "password": registered_user["password"],
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["token_type"] == "bearer"
    # A JWT is header.payload.signature
    assert body["access_token"].count(".") == 2


def test_login_rejects_wrong_password(client: TestClient, registered_user: dict) -> None:
    response = client.post(
        "/api/v1/auth/login",
        data={"username": registered_user["email"], "password": "wrong-password"},
    )

    assert response.status_code == 401


def test_login_error_does_not_reveal_whether_account_exists(
    client: TestClient, registered_user: dict
) -> None:
    """Both failure modes must be indistinguishable.

    If "no such user" and "wrong password" differed, anyone could
    enumerate which email addresses have accounts.
    """
    no_such_user = client.post(
        "/api/v1/auth/login",
        data={"username": "nobody@example.com", "password": "whatever"},
    )
    wrong_password = client.post(
        "/api/v1/auth/login",
        data={"username": registered_user["email"], "password": "wrong-password"},
    )

    assert no_such_user.status_code == wrong_password.status_code == 401
    assert no_such_user.json() == wrong_password.json()


def test_me_returns_current_user(
    client: TestClient, registered_user: dict, auth_headers: dict
) -> None:
    response = client.get("/api/v1/auth/me", headers=auth_headers)

    assert response.status_code == 200
    assert response.json()["email"] == registered_user["email"]


def test_me_requires_a_token(client: TestClient) -> None:
    response = client.get("/api/v1/auth/me")

    assert response.status_code == 401


def test_me_rejects_a_forged_token(client: TestClient) -> None:
    """A token not signed with our secret must be refused.

    This is the property the whole auth scheme rests on: possession of
    a token proves nothing unless its signature verifies.
    """
    response = client.get(
        "/api/v1/auth/me",
        headers={"Authorization": "Bearer not.a.real.token"},
    )

    assert response.status_code == 401
