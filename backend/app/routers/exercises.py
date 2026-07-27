"""Exercise analytics endpoints.

A "router" groups related endpoints into their own file. Without it,
main.py becomes a 2000-line dumping ground. main.py imports this and
registers it with app.include_router().
"""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import text
from sqlalchemy.engine import Connection

from app.db import get_connection
from app.dependencies import get_current_user
from app.schemas import ExerciseOut, VolumePoint

# prefix is prepended to every path below, so the route defined as
# "/{exercise_id}/volume" is served at
# /api/v1/exercises/{exercise_id}/volume
router = APIRouter(prefix="/api/v1/exercises", tags=["exercises"])


@router.get("", response_model=list[ExerciseOut])
def list_exercises(conn: Connection = Depends(get_connection)) -> list[dict]:
    """Every global exercise, so you can find the ID you need.

    `response_model=list[ExerciseOut]` is the new part. FastAPI now:
      1. validates every row against ExerciseOut before sending it,
      2. drops any column not declared there,
      3. publishes the shape in /docs and /openapi.json.

    Point 2 is a security feature, not a convenience. When this table
    eventually holds columns you do not want public, forgetting to
    strip them is no longer possible -- anything undeclared simply
    does not go out.

    .mappings() makes each row behave like a dict rather than a tuple,
    which is what Pydantic validates against.
    """
    rows = conn.execute(
        text(
            """
            SELECT id, name, category, equipment
            FROM exercises
            WHERE created_by_user_id IS NULL
            ORDER BY name;
            """
        )
    ).mappings().all()

    return [dict(row) for row in rows]


@router.get("/{exercise_id}/volume", response_model=list[VolumePoint])
def exercise_volume(
    exercise_id: int,
    weeks: int = Query(8, ge=1, le=52, description="How far back to look"),
    conn: Connection = Depends(get_connection),
    current_user: dict = Depends(get_current_user),
) -> list[dict]:
    """Per-session working volume for one exercise, for the logged-in user.

    Warmup sets are excluded. Volume is weight x reps summed across
    every working set in the session.
    """
    # NOTE ON :placeholders -- never build SQL with f-strings.
    # f"... WHERE exercise_id = {exercise_id}" would let an attacker
    # close the quote and append their own SQL (`x'; DROP TABLE users; --`).
    # With placeholders the query and the values travel to Postgres
    # separately: Postgres parses the query first, then slots the
    # values in as data, so a value can never become executable SQL.
    # Rule with no exceptions: values go in the params dict below.
    sql = text(
        """
        SELECT performed_on,
               SUM(volume_kg) AS session_volume,
               MAX(weight_kg) AS top_weight
        FROM v_set_details
        WHERE exercise_id = :exercise_id
          AND user_id = :user_id
          AND performed_on >= CURRENT_DATE - make_interval(weeks => :weeks)
          AND is_warmup = false
        GROUP BY performed_on
        ORDER BY performed_on;
        """
    )

    rows = conn.execute(
        sql,
        {
            "exercise_id": exercise_id,
            "weeks": weeks,
            # The scoping that makes this endpoint safe. Without it,
            # any logged-in user could read every other user's
            # training history.
            "user_id": current_user["id"],
        },
    ).mappings().all()

    if not rows:
        # Returning [] would be ambiguous: no data, or no such exercise?
        # 404 says clearly "that thing does not exist".
        raise HTTPException(
            status_code=404,
            detail=f"No volume data for exercise {exercise_id} in the last {weeks} weeks.",
        )

    return [dict(row) for row in rows]
