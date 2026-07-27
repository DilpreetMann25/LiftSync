"""Password hashing and JWT access tokens.

Two separate ideas that often get muddled:

  HASHING  -- how a password is STORED, so a database leak does not
              hand an attacker everyone's password.
  TOKENS   -- how a user stays logged in after the password check,
              so they do not resend credentials on every request.

===================================================================
WHY HASHING, NOT ENCRYPTION
===================================================================
Encryption is reversible: with the key you get the original back.
That is exactly wrong for passwords -- if your server can recover
them, so can anyone who steals your key.

Hashing is one-way. bcrypt turns "hunter2" into a fixed-length string
that cannot be reversed. To check a login you hash the attempt and
compare hashes. The plaintext is never stored, and you cannot email a
user their forgotten password -- only let them set a new one. That
inability IS the security property.

bcrypt also does two things a plain hash like SHA-256 does not:

  SALT -- random bytes mixed into every hash, stored alongside it.
  Two users with the same password get different hashes, so an
  attacker cannot spot repeats or use precomputed rainbow tables.

  COST -- bcrypt is deliberately slow (~100ms). Irrelevant for one
  login, brutal for someone brute-forcing billions of guesses. The
  cost factor can be raised as hardware gets faster.
"""

from datetime import datetime, timedelta, timezone

import bcrypt
import jwt

from app.config import ACCESS_TOKEN_EXPIRE_MINUTES, JWT_ALGORITHM, JWT_SECRET_KEY

# bcrypt truncates anything past 72 BYTES (not characters -- an emoji
# is 4). Silently ignoring the rest of a long passphrase would make it
# weaker than the user believes, so we reject instead.
MAX_PASSWORD_BYTES = 72


def hash_password(plain_password: str) -> str:
    """Hash a password for storage. Never store the plaintext."""
    encoded = plain_password.encode("utf-8")
    if len(encoded) > MAX_PASSWORD_BYTES:
        raise ValueError(f"Password must be at most {MAX_PASSWORD_BYTES} bytes.")
    return bcrypt.hashpw(encoded, bcrypt.gensalt()).decode("utf-8")


def verify_password(plain_password: str, password_hash: str) -> bool:
    """Check a login attempt against a stored hash.

    bcrypt.checkpw reads the salt and cost out of the stored hash,
    re-hashes the attempt the same way, and compares in constant time
    -- meaning it takes the same duration whether the first character
    is wrong or only the last. A naive `==` leaks information through
    timing that can be measured over many attempts.
    """
    encoded = plain_password.encode("utf-8")
    if len(encoded) > MAX_PASSWORD_BYTES:
        return False
    try:
        return bcrypt.checkpw(encoded, password_hash.encode("utf-8"))
    except ValueError:
        # Malformed hash in the database -- treat as a failed login
        # rather than crashing the endpoint.
        return False


# ===================================================================
# JWT: JSON Web Tokens
# ===================================================================
# A JWT is three base64 chunks separated by dots:
#
#     header.payload.signature
#
# The payload is NOT encrypted -- anyone can decode and read it. Paste
# one into jwt.io and you will see its contents in plaintext. So never
# put anything secret in a token.
#
# What it IS is TAMPER-PROOF. The signature is computed from the
# payload plus your JWT_SECRET_KEY. Change one character of the
# payload and the signature no longer matches. Forging a token
# requires the secret.
#
# Why bother instead of a session in the database? Because the server
# can verify a token with maths alone -- no database lookup on every
# request. The tradeoff: you cannot easily revoke one. Logging out
# discards the token client-side, but a stolen token stays valid until
# it expires. That is why expiry is short.
# ===================================================================


def create_access_token(user_id: int) -> str:
    """Issue a signed token identifying this user."""
    now = datetime.now(timezone.utc)
    payload = {
        # "sub" (subject) is the standard claim for "who is this".
        # JWT requires it to be a string, even for numeric IDs.
        "sub": str(user_id),
        "iat": now,                                              # issued at
        "exp": now + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES),  # expires
    }
    return jwt.encode(payload, JWT_SECRET_KEY, algorithm=JWT_ALGORITHM)


def decode_access_token(token: str) -> int | None:
    """Verify a token and return its user id, or None if invalid.

    jwt.decode does the security work: checks the signature against
    our secret and rejects anything expired. We pass algorithms
    explicitly -- accepting whatever the token claims would allow the
    classic "alg: none" forgery, where an attacker submits an unsigned
    token and a careless library accepts it.
    """
    try:
        payload = jwt.decode(token, JWT_SECRET_KEY, algorithms=[JWT_ALGORITHM])
    except jwt.PyJWTError:
        return None

    subject = payload.get("sub")
    if subject is None:
        return None

    try:
        return int(subject)
    except (TypeError, ValueError):
        return None
