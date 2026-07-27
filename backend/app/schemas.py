"""Pydantic schemas — the shape of data crossing the API boundary.

WHAT THESE ARE FOR
------------------
A Pydantic model is a class that declares what data must look like.
Pydantic then enforces it: converting types where it safely can,
raising errors where it cannot.

You already have this idea in the database -- CHECK constraints,
NOT NULL, foreign keys. Schemas are the same instinct applied at the
other edge of the app:

    outside world  ──▶  [ Pydantic ]  ──▶  your code
                                      ──▶  [ Pydantic ]  ──▶ outside world

Nothing untyped gets in, nothing unshaped gets out.

NAMING
------
`...Out` = something the API returns.
`...In`  = something the API accepts (starting in the write endpoints).

Keeping them separate matters more than it looks. UserIn will accept a
plaintext password; UserOut must never contain a password hash. One
shared model would make leaking it a one-line mistake.
"""

from datetime import date

from pydantic import BaseModel, EmailStr, Field


# ---------------------------------------------------------------
# Auth
# ---------------------------------------------------------------
class UserIn(BaseModel):
    """Registration payload — what a new user SENDS."""

    # EmailStr rejects anything that is not a valid address before
    # your code runs. One annotation replaces a regex you would
    # otherwise write badly.
    email: EmailStr
    password: str = Field(..., min_length=8, max_length=72)
    display_name: str = Field(..., min_length=1, max_length=100)
    height_cm: float | None = Field(None, gt=0, lt=300)


class UserOut(BaseModel):
    """User data the API RETURNS.

    Note what is absent: password, password_hash. This is why In and
    Out are separate classes. Sharing one model between them is how
    password hashes end up in JSON responses -- and because Pydantic
    drops undeclared fields, leaking one here is not an oversight you
    can make by accident.
    """

    id: int
    email: EmailStr
    display_name: str
    height_cm: float | None = None


class Token(BaseModel):
    """What the login endpoint returns."""

    access_token: str
    # "bearer" is the standard scheme: the client sends
    # `Authorization: Bearer <token>` on subsequent requests.
    token_type: str = "bearer"


class ExerciseOut(BaseModel):
    """A movement from the exercise dictionary."""

    id: int
    name: str
    category: str
    equipment: str | None = None   # nullable in the database, optional here


class VolumePoint(BaseModel):
    """One training session's working volume for a single exercise."""

    performed_on: date

    # Declaring these as float is what fixes the "935.00" strings.
    # Postgres NUMERIC arrives in Python as Decimal, which has no JSON
    # equivalent, so FastAPI was serialising it as a string to avoid
    # silently changing the value. Saying float here makes the
    # conversion explicit and intentional.
    #
    # Is losing exactness acceptable? Here, yes: this is a chart
    # value, read once and thrown away. It would NOT be acceptable for
    # money, or for anything written back to the database. Storage
    # stays NUMERIC; only transport is float.
    session_volume: float = Field(..., description="Sum of weight x reps, warmups excluded")
    top_weight: float = Field(..., description="Heaviest working set that session")
