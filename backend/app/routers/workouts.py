"""Workout logging — the first endpoints that WRITE data.

Everything before this only read rows a script had put there. Writing
introduces a problem reading never had: a request can fail halfway.

A workout insert is not one statement. It is:

    1 workout row
  + N workout_exercises rows
  + M sets rows

If row 1 succeeds and the sets fail on number 7, you must not be left
with a workout containing six sets. That is what transactions are for,
and it is the same BEGIN/COMMIT idea as the migrations — applied once
per HTTP request instead of once per deployment.
"""

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import text
from sqlalchemy.engine import Connection

from app.db import get_connection
from app.dependencies import get_current_user
from app.schemas import WorkoutIn, WorkoutOut, WorkoutSummary

router = APIRouter(prefix="/api/v1/workouts", tags=["workouts"])


def _load_workout(conn: Connection, workout_id: int, user_id: int) -> dict | None:
    """Fetch one workout with all its exercises and sets.

    TWO queries, not one per exercise. Looping over exercises and
    querying sets for each would be the N+1 problem: a 6-exercise
    workout becomes 7 round-trips instead of 2. It looks fine on your
    laptop with local Postgres and falls apart against RDS across a
    network. Fetch flat, assemble in Python.
    """
    workout = conn.execute(
        text(
            """
            SELECT id, performed_on, notes
            FROM workouts
            WHERE id = :workout_id AND user_id = :user_id;
            """
        ),
        {"workout_id": workout_id, "user_id": user_id},
    ).mappings().first()

    if workout is None:
        return None

    # LEFT JOIN, not JOIN: an exercise with no sets should still
    # appear rather than silently vanishing from the response.
    rows = conn.execute(
        text(
            """
            SELECT we.id            AS we_id,
                   we.exercise_id,
                   e.name           AS exercise_name,
                   we.order_index,
                   we.superset_group,
                   we.notes         AS we_notes,
                   s.id             AS set_id,
                   s.set_number,
                   s.weight_kg,
                   s.reps,
                   s.rpe,
                   s.is_warmup,
                   s.volume_kg
            FROM workout_exercises we
            JOIN exercises e ON e.id = we.exercise_id
            LEFT JOIN sets s ON s.workout_exercise_id = we.id
            WHERE we.workout_id = :workout_id
            ORDER BY we.order_index, s.set_number;
            """
        ),
        {"workout_id": workout_id},
    ).mappings().all()

    # Flat rows -> nested structure. Dict keyed by workout_exercise id
    # preserves insertion order (guaranteed in Python 3.7+), and the
    # ORDER BY above means insertion order is already correct.
    exercises: dict[int, dict] = {}
    total_volume = 0.0

    for row in rows:
        we_id = row["we_id"]
        if we_id not in exercises:
            exercises[we_id] = {
                "id": we_id,
                "exercise_id": row["exercise_id"],
                "exercise_name": row["exercise_name"],
                "order_index": row["order_index"],
                "superset_group": row["superset_group"],
                "notes": row["we_notes"],
                "sets": [],
            }

        if row["set_id"] is not None:
            exercises[we_id]["sets"].append(
                {
                    "id": row["set_id"],
                    "set_number": row["set_number"],
                    "weight_kg": float(row["weight_kg"]),
                    "reps": row["reps"],
                    "rpe": float(row["rpe"]) if row["rpe"] is not None else None,
                    "is_warmup": row["is_warmup"],
                    "volume_kg": float(row["volume_kg"]),
                }
            )
            if not row["is_warmup"]:
                total_volume += float(row["volume_kg"])

    return {
        "id": workout["id"],
        "performed_on": workout["performed_on"],
        "notes": workout["notes"],
        "total_volume_kg": round(total_volume, 2),
        "exercises": list(exercises.values()),
    }


@router.post("", response_model=WorkoutOut, status_code=status.HTTP_201_CREATED)
def create_workout(
    payload: WorkoutIn,
    conn: Connection = Depends(get_connection),
    current_user: dict = Depends(get_current_user),
) -> dict:
    """Log a training session.

    Pydantic has already validated the whole nested payload before
    this function runs — rep counts, weights, at least one exercise,
    at least one set each. Anything malformed was rejected with a 422
    that named the exact field.
    """
    user_id = current_user["id"]

    # Validate every exercise id in ONE query rather than per-exercise.
    # The visibility check matters: a user may reference a global
    # exercise or their own custom one, never someone else's.
    requested_ids = {ex.exercise_id for ex in payload.exercises}
    valid_ids = set(
        conn.execute(
            text(
                """
                SELECT id FROM exercises
                WHERE id = ANY(:ids)
                  AND (created_by_user_id IS NULL OR created_by_user_id = :user_id);
                """
            ),
            {"ids": list(requested_ids), "user_id": user_id},
        ).scalars().all()
    )

    unknown = requested_ids - valid_ids
    if unknown:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unknown or inaccessible exercise ids: {sorted(unknown)}",
        )

    try:
        workout_id = conn.execute(
            text(
                """
                INSERT INTO workouts (user_id, performed_on, notes)
                VALUES (:user_id, :performed_on, :notes)
                RETURNING id;
                """
            ),
            {
                "user_id": user_id,
                "performed_on": payload.performed_on,
                "notes": payload.notes,
            },
        ).scalar_one()

        for order_index, exercise in enumerate(payload.exercises):
            we_id = conn.execute(
                text(
                    """
                    INSERT INTO workout_exercises
                        (workout_id, exercise_id, order_index, superset_group, notes)
                    VALUES (:workout_id, :exercise_id, :order_index, :superset_group, :notes)
                    RETURNING id;
                    """
                ),
                {
                    "workout_id": workout_id,
                    "exercise_id": exercise.exercise_id,
                    # Position in the session comes from list order.
                    # This is also what lets the same exercise appear
                    # twice as two distinct blocks.
                    "order_index": order_index,
                    "superset_group": exercise.superset_group,
                    "notes": exercise.notes,
                },
            ).scalar_one()

            for set_number, s in enumerate(exercise.sets, start=1):
                conn.execute(
                    text(
                        """
                        INSERT INTO sets
                            (workout_exercise_id, set_number, weight_kg,
                             reps, rpe, is_warmup)
                        VALUES (:we_id, :set_number, :weight_kg,
                                :reps, :rpe, :is_warmup);
                        """
                    ),
                    {
                        "we_id": we_id,
                        "set_number": set_number,
                        "weight_kg": s.weight_kg,
                        "reps": s.reps,
                        "rpe": s.rpe,
                        "is_warmup": s.is_warmup,
                    },
                )

        # Nothing above is durable until this line. Every INSERT so far
        # is provisional -- visible to this connection, invisible to
        # everyone else, and discarded if anything raises.
        conn.commit()

    except Exception:
        # Undo everything. A half-saved workout is worse than a failed
        # request: the user sees an error, assumes nothing happened,
        # and now has corrupt history they will never notice.
        conn.rollback()
        raise

    created = _load_workout(conn, workout_id, user_id)
    if created is None:  # pragma: no cover — should be unreachable
        raise HTTPException(status_code=500, detail="Workout vanished after creation.")

    return created


@router.get("", response_model=list[WorkoutSummary])
def list_workouts(
    limit: int = Query(30, ge=1, le=200),
    offset: int = Query(0, ge=0),
    conn: Connection = Depends(get_connection),
    current_user: dict = Depends(get_current_user),
) -> list[dict]:
    """Recent sessions, newest first.

    Paginated. An endpoint returning "all" of anything is a bug
    waiting for a user with three years of history -- it will
    eventually try to serialise 100MB of JSON and time out.
    """
    rows = conn.execute(
        text(
            """
            SELECT w.id,
                   w.performed_on,
                   COUNT(DISTINCT we.id)                                  AS exercise_count,
                   COUNT(s.id)                                            AS set_count,
                   COALESCE(SUM(s.volume_kg) FILTER (WHERE NOT s.is_warmup), 0) AS total_volume_kg
            FROM workouts w
            LEFT JOIN workout_exercises we ON we.workout_id = w.id
            LEFT JOIN sets s               ON s.workout_exercise_id = we.id
            WHERE w.user_id = :user_id
            GROUP BY w.id, w.performed_on
            ORDER BY w.performed_on DESC, w.id DESC
            LIMIT :limit OFFSET :offset;
            """
        ),
        {"user_id": current_user["id"], "limit": limit, "offset": offset},
    ).mappings().all()

    # FILTER (WHERE ...) above is worth knowing: it applies a condition
    # to ONE aggregate without affecting the others. A plain WHERE
    # excluding warmups would also shrink set_count.
    return [dict(row) for row in rows]


@router.get("/{workout_id}", response_model=WorkoutOut)
def get_workout(
    workout_id: int,
    conn: Connection = Depends(get_connection),
    current_user: dict = Depends(get_current_user),
) -> dict:
    """One session, fully expanded."""
    workout = _load_workout(conn, workout_id, current_user["id"])

    # 404 covers both "does not exist" and "belongs to someone else".
    # A 403 would confirm the workout exists, which leaks information.
    if workout is None:
        raise HTTPException(status_code=404, detail="Workout not found.")

    return workout


@router.delete("/{workout_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_workout(
    workout_id: int,
    conn: Connection = Depends(get_connection),
    current_user: dict = Depends(get_current_user),
) -> None:
    """Delete a session and everything in it.

    One DELETE removes the workout, its workout_exercises, and all
    their sets — via ON DELETE CASCADE declared back in migration
    0001. The database handles the cleanup; forgetting a child table
    is not a mistake you can make here.

    204 No Content: succeeded, nothing to return.
    """
    result = conn.execute(
        text("DELETE FROM workouts WHERE id = :workout_id AND user_id = :user_id;"),
        {"workout_id": workout_id, "user_id": current_user["id"]},
    )
    conn.commit()

    # rowcount tells you whether anything was actually deleted. Without
    # checking, deleting someone else's workout id would return a
    # cheerful 204 while doing nothing.
    if result.rowcount == 0:
        raise HTTPException(status_code=404, detail="Workout not found.")
