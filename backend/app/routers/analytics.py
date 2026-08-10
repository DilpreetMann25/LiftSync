"""Analytics endpoints.

Deliberately thin. Each route does three things: take the request,
call a function in app/analytics.py, return the result. All the
interesting logic lives in that module, where it can be tested
directly and called by the AI agent in Phase 5 without going over HTTP.
"""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.engine import Connection

from app import analytics
from app.db import get_connection
from app.dependencies import get_current_user
from app.schemas import MuscleVolumePoint, PlateauReport, ProgressionPoint

router = APIRouter(prefix="/api/v1/analytics", tags=["analytics"])


@router.get("/exercises/{exercise_id}/progression", response_model=list[ProgressionPoint])
def exercise_progression(
    exercise_id: int,
    weeks: int = Query(12, ge=1, le=104),
    conn: Connection = Depends(get_connection),
    current_user: dict = Depends(get_current_user),
) -> list[dict]:
    """Strength trend for one lift, session by session.

    Returns estimated 1RM per session plus a rolling average and the
    change from the previous session — enough to draw a progression
    chart, and enough for the AI coach to see whether a lift is moving.
    """
    points = analytics.exercise_progression(
        conn, user_id=current_user["id"], exercise_id=exercise_id, weeks=weeks
    )

    if not points:
        raise HTTPException(
            status_code=404,
            detail=f"No training data for exercise {exercise_id} in the last {weeks} weeks.",
        )

    return points


@router.get("/plateaus", response_model=list[PlateauReport])
def plateaus(
    stall_weeks: int = Query(3, ge=1, le=12, description="Weeks without a new best"),
    conn: Connection = Depends(get_connection),
    current_user: dict = Depends(get_current_user),
) -> list[dict]:
    """Lifts that have stopped progressing.

    A lift is plateaued when its best estimated 1RM in the last
    `stall_weeks` is no higher than its best before that.

    An empty list is a valid, meaningful answer here — it means
    everything is progressing. No 404: the question was answered.
    """
    return analytics.detect_plateaus(
        conn, user_id=current_user["id"], stall_weeks=stall_weeks
    )


@router.get("/muscle-volume", response_model=list[MuscleVolumePoint])
def muscle_volume(
    weeks: int = Query(8, ge=1, le=52),
    muscle_group: str | None = Query(None, description="e.g. front_delts"),
    conn: Connection = Depends(get_connection),
    current_user: dict = Depends(get_current_user),
) -> list[dict]:
    """Weighted training volume per muscle group per week.

    Volume is weighted by each exercise's contribution to the muscle —
    bench press counts 100% toward chest but 40% toward front delts.

    The current, incomplete week is excluded. Including it makes every
    chart look like a sudden collapse in training volume.
    """
    return analytics.weekly_muscle_volume(
        conn, user_id=current_user["id"], weeks=weeks, muscle_group=muscle_group
    )
