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

from pydantic import BaseModel, Field


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
