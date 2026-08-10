"""Tests for e1RM progression, plateau detection, and muscle volume.

These build their own training history rather than relying on the seed
script. Two reasons:

  1. Seed data is random-ish and dated relative to when it ran. A test
     depending on it would pass today and fail next month.
  2. To test a plateau you need data that IS plateaued, precisely and
     on purpose. Constructing it makes the intent obvious.

Dates are all relative to today, since the detector compares against
CURRENT_DATE.
"""

from datetime import date, timedelta

from fastapi.testclient import TestClient


def log_session(
    client: TestClient,
    headers: dict,
    exercise_id: int,
    days_ago: int,
    weight: float,
    reps: int = 5,
) -> None:
    """Log a single-exercise, single-set session on a specific date."""
    payload = {
        "performed_on": (date.today() - timedelta(days=days_ago)).isoformat(),
        "exercises": [
            {
                "exercise_id": exercise_id,
                "sets": [{"weight_kg": weight, "reps": reps, "is_warmup": False}],
            }
        ],
    }
    response = client.post("/api/v1/workouts", json=payload, headers=headers)
    assert response.status_code == 201, response.text


# ---------------------------------------------------------------
# Progression
# ---------------------------------------------------------------


def test_progression_computes_epley_e1rm(
    client: TestClient, auth_headers: dict, exercise_ids: dict
) -> None:
    """100kg x 5 -> 100 * (1 + 5/30) = 116.67, rounded to 116.7."""
    bench = exercise_ids["Barbell Bench Press"]
    log_session(client, auth_headers, bench, days_ago=7, weight=100, reps=5)

    body = client.get(
        f"/api/v1/analytics/exercises/{bench}/progression?weeks=4", headers=auth_headers
    ).json()

    assert body[0]["e1rm"] == 116.7


def test_progression_change_is_null_for_first_session(
    client: TestClient, auth_headers: dict, exercise_ids: dict
) -> None:
    """LAG has no previous row to look at, so the change is NULL."""
    bench = exercise_ids["Barbell Bench Press"]
    log_session(client, auth_headers, bench, days_ago=14, weight=100)
    log_session(client, auth_headers, bench, days_ago=7, weight=105)

    body = client.get(
        f"/api/v1/analytics/exercises/{bench}/progression?weeks=4", headers=auth_headers
    ).json()

    assert body[0]["change_from_previous"] is None
    assert body[1]["change_from_previous"] > 0


def test_progression_best_to_date_never_decreases(
    client: TestClient, auth_headers: dict, exercise_ids: dict
) -> None:
    """A running maximum must be monotonic, even when a session is worse."""
    bench = exercise_ids["Barbell Bench Press"]
    log_session(client, auth_headers, bench, days_ago=21, weight=100)
    log_session(client, auth_headers, bench, days_ago=14, weight=110)
    log_session(client, auth_headers, bench, days_ago=7, weight=90)

    body = client.get(
        f"/api/v1/analytics/exercises/{bench}/progression?weeks=8", headers=auth_headers
    ).json()

    bests = [point["best_e1rm_to_date"] for point in body]
    assert bests == sorted(bests)
    assert bests[-1] == bests[1]  # the bad session did not lower it


def test_progression_requires_authentication(
    client: TestClient, exercise_ids: dict
) -> None:
    response = client.get(
        f"/api/v1/analytics/exercises/{exercise_ids['Barbell Bench Press']}/progression"
    )

    assert response.status_code == 401


# ---------------------------------------------------------------
# Plateau detection
# ---------------------------------------------------------------


def test_plateau_detected_when_no_new_best(
    client: TestClient, auth_headers: dict, exercise_ids: dict
) -> None:
    """Six sessions at the same weight across five weeks.

    Best-in-recent-window equals best-before-it, so the lift is stalled.
    """
    ohp = exercise_ids["Overhead Press"]
    for days_ago in (35, 30, 25, 18, 12, 6):
        log_session(client, auth_headers, ohp, days_ago=days_ago, weight=60)

    body = client.get("/api/v1/analytics/plateaus?stall_weeks=3", headers=auth_headers).json()

    names = [row["exercise_name"] for row in body]
    assert "Overhead Press" in names


def test_no_plateau_while_still_progressing(
    client: TestClient, auth_headers: dict, exercise_ids: dict
) -> None:
    """Same schedule, but the recent sessions are heavier."""
    ohp = exercise_ids["Overhead Press"]
    for days_ago in (35, 30, 25):
        log_session(client, auth_headers, ohp, days_ago=days_ago, weight=60)
    for days_ago in (18, 12, 6):
        log_session(client, auth_headers, ohp, days_ago=days_ago, weight=65)

    body = client.get("/api/v1/analytics/plateaus?stall_weeks=3", headers=auth_headers).json()

    assert body == []


def test_isolation_lifts_get_a_longer_window(
    client: TestClient, auth_headers: dict, exercise_ids: dict
) -> None:
    """THE REGRESSION TEST for the false positives found on real data.

    Identical stall pattern to test_plateau_detected_when_no_new_best,
    but on an isolation movement. With a 3-week window it would be
    flagged; isolation gets 6 weeks, so it must not be.

    Accessories are programmed to progress monthly. Judging them on the
    same clock as a squat flags lifts that are perfectly on schedule.
    """
    raise_id = exercise_ids["Dumbbell Lateral Raise"]
    for days_ago in (35, 30, 25, 18, 12, 6):
        log_session(client, auth_headers, raise_id, days_ago=days_ago, weight=12.5, reps=12)

    body = client.get("/api/v1/analytics/plateaus?stall_weeks=3", headers=auth_headers).json()

    names = [row["exercise_name"] for row in body]
    assert "Dumbbell Lateral Raise" not in names


def test_plateau_report_explains_the_window_used(
    client: TestClient, auth_headers: dict, exercise_ids: dict
) -> None:
    ohp = exercise_ids["Overhead Press"]
    for days_ago in (35, 30, 25, 18, 12, 6):
        log_session(client, auth_headers, ohp, days_ago=days_ago, weight=60)

    row = client.get(
        "/api/v1/analytics/plateaus?stall_weeks=3", headers=auth_headers
    ).json()[0]

    assert row["category"] == "compound"
    assert row["stall_weeks_applied"] == 3


def test_lift_trained_too_rarely_is_not_flagged(
    client: TestClient, auth_headers: dict, exercise_ids: dict
) -> None:
    """min_recent_sessions guard: two sessions is not evidence of a stall."""
    ohp = exercise_ids["Overhead Press"]
    log_session(client, auth_headers, ohp, days_ago=35, weight=60)
    log_session(client, auth_headers, ohp, days_ago=10, weight=60)

    body = client.get("/api/v1/analytics/plateaus?stall_weeks=3", headers=auth_headers).json()

    assert body == []


def test_brand_new_lift_is_not_a_plateau(
    client: TestClient, auth_headers: dict, exercise_ids: dict
) -> None:
    """No history before the recent window means nothing to compare to."""
    ohp = exercise_ids["Overhead Press"]
    for days_ago in (12, 8, 4):
        log_session(client, auth_headers, ohp, days_ago=days_ago, weight=60)

    body = client.get("/api/v1/analytics/plateaus?stall_weeks=3", headers=auth_headers).json()

    assert body == []


def test_plateaus_are_scoped_to_the_current_user(
    client: TestClient, auth_headers: dict, exercise_ids: dict
) -> None:
    ohp = exercise_ids["Overhead Press"]
    for days_ago in (35, 30, 25, 18, 12, 6):
        log_session(client, auth_headers, ohp, days_ago=days_ago, weight=60)

    client.post(
        "/api/v1/auth/register",
        json={
            "email": "stranger@example.com",
            "password": "stranger-password",
            "display_name": "Stranger",
        },
    )
    token = client.post(
        "/api/v1/auth/login",
        data={"username": "stranger@example.com", "password": "stranger-password"},
    ).json()["access_token"]

    body = client.get(
        "/api/v1/analytics/plateaus", headers={"Authorization": f"Bearer {token}"}
    ).json()

    assert body == []


# ---------------------------------------------------------------
# Muscle volume
# ---------------------------------------------------------------


def test_muscle_volume_is_weighted_by_contribution(
    client: TestClient, auth_headers: dict, exercise_ids: dict
) -> None:
    """Bench press contributes 1.00 to chest but only 0.40 to front delts.

    100kg x 5 = 500kg of volume -> 500 chest, 200 front delts.
    """
    bench = exercise_ids["Barbell Bench Press"]
    log_session(client, auth_headers, bench, days_ago=14, weight=100, reps=5)

    body = client.get("/api/v1/analytics/muscle-volume?weeks=8", headers=auth_headers).json()
    by_muscle = {row["muscle_group"]: row["weighted_volume"] for row in body}

    assert by_muscle["chest"] == 500.0
    assert by_muscle["front_delts"] == 200.0


def test_muscle_volume_excludes_the_current_partial_week(
    client: TestClient, auth_headers: dict, exercise_ids: dict
) -> None:
    """The reporting bug spotted in Phase 1.

    An incomplete week sitting beside complete ones looks like a
    collapse in training volume. It is excluded rather than shown.
    """
    bench = exercise_ids["Barbell Bench Press"]
    log_session(client, auth_headers, bench, days_ago=0, weight=100, reps=5)

    body = client.get("/api/v1/analytics/muscle-volume?weeks=8", headers=auth_headers).json()

    assert body == []


def test_muscle_volume_can_filter_to_one_group(
    client: TestClient, auth_headers: dict, exercise_ids: dict
) -> None:
    bench = exercise_ids["Barbell Bench Press"]
    log_session(client, auth_headers, bench, days_ago=14, weight=100, reps=5)

    body = client.get(
        "/api/v1/analytics/muscle-volume?weeks=8&muscle_group=front_delts",
        headers=auth_headers,
    ).json()

    assert {row["muscle_group"] for row in body} == {"front_delts"}


def test_muscle_volume_excludes_warmups(
    client: TestClient, auth_headers: dict, exercise_ids: dict
) -> None:
    bench = exercise_ids["Barbell Bench Press"]
    payload = {
        "performed_on": (date.today() - timedelta(days=14)).isoformat(),
        "exercises": [
            {
                "exercise_id": bench,
                "sets": [
                    {"weight_kg": 60, "reps": 10, "is_warmup": True},
                    {"weight_kg": 100, "reps": 5, "is_warmup": False},
                ],
            }
        ],
    }
    client.post("/api/v1/workouts", json=payload, headers=auth_headers)

    body = client.get("/api/v1/analytics/muscle-volume?weeks=8", headers=auth_headers).json()
    chest = next(row for row in body if row["muscle_group"] == "chest")

    # The 600kg warmup must not appear.
    assert chest["weighted_volume"] == 500.0
    assert chest["working_sets"] == 1
