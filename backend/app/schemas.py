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


# ---------------------------------------------------------------
# Workout logging — nested models
# ---------------------------------------------------------------
# A workout contains exercises, which contain sets. Pydantic models
# nest the same way, so ONE declaration validates the whole tree:
# reject a workout with 200 reps on set 3 of exercise 2, and the
# error tells you exactly that.
#
# Every bound here (ge, le, gt) duplicates a CHECK constraint in the
# database. Deliberate. The database guarantees nothing bad is ever
# STORED; these bounds mean the user gets a clear 422 explaining what
# was wrong, instead of an opaque 500 from a constraint violation.
# Two layers, two different jobs.


class SetIn(BaseModel):
    """One set as submitted by the client."""

    weight_kg: float = Field(..., ge=0, le=1000)
    reps: int = Field(..., gt=0, le=100)
    rpe: float | None = Field(None, ge=1, le=10)
    is_warmup: bool = False


class WorkoutExerciseIn(BaseModel):
    """One exercise within a workout, plus its sets.

    No set_number field: the client sends sets in order and the server
    numbers them. Letting clients choose would invite duplicates and
    gaps, and the ordering is not theirs to decide.
    """

    exercise_id: int
    superset_group: int | None = Field(
        None, ge=0, description="Exercises sharing a value were performed alternating"
    )
    notes: str | None = None
    sets: list[SetIn] = Field(..., min_length=1)


class WorkoutIn(BaseModel):
    """A complete training session as submitted by the client."""

    performed_on: date
    notes: str | None = None
    # min_length=1: a workout with no exercises is not a workout.
    exercises: list[WorkoutExerciseIn] = Field(..., min_length=1)


class SetOut(BaseModel):
    id: int
    set_number: int
    weight_kg: float
    reps: int
    rpe: float | None = None
    is_warmup: bool
    # Computed by Postgres, never sent by the client.
    volume_kg: float


class WorkoutExerciseOut(BaseModel):
    id: int
    exercise_id: int
    exercise_name: str
    order_index: int
    superset_group: int | None = None
    notes: str | None = None
    sets: list[SetOut]


class WorkoutOut(BaseModel):
    """A full session with everything in it."""

    id: int
    performed_on: date
    notes: str | None = None
    total_volume_kg: float = Field(..., description="Working sets only, warmups excluded")
    exercises: list[WorkoutExerciseOut]


class WorkoutSummary(BaseModel):
    """A session without its sets — for list views.

    Returning full nested detail for every workout in a list would be
    slow and mostly wasted. Separate read models for list and detail
    is standard API design.
    """

    id: int
    performed_on: date
    exercise_count: int
    set_count: int
    total_volume_kg: float


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
