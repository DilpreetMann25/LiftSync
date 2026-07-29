"""Tests for workout logging, retrieval, and access control."""

from fastapi.testclient import TestClient


def build_payload(exercise_ids: dict[str, int]) -> dict:
    """A realistic two-exercise session with one warmup set."""
    return {
        "performed_on": "2026-07-28",
        "notes": "Test session",
        "exercises": [
            {
                "exercise_id": exercise_ids["Overhead Press"],
                "sets": [
                    {"weight_kg": 40, "reps": 8, "is_warmup": True},
                    {"weight_kg": 60, "reps": 5, "rpe": 8, "is_warmup": False},
                    {"weight_kg": 60, "reps": 5, "rpe": 9, "is_warmup": False},
                ],
            },
            {
                "exercise_id": exercise_ids["Barbell Bench Press"],
                "sets": [
                    {"weight_kg": 90, "reps": 5, "rpe": 8.5, "is_warmup": False},
                ],
            },
        ],
    }


def test_create_workout_returns_nested_structure(
    client: TestClient, auth_headers: dict, exercise_ids: dict
) -> None:
    response = client.post(
        "/api/v1/workouts", json=build_payload(exercise_ids), headers=auth_headers
    )

    assert response.status_code == 201
    body = response.json()
    assert body["performed_on"] == "2026-07-28"
    assert len(body["exercises"]) == 2
    assert len(body["exercises"][0]["sets"]) == 3


def test_set_numbers_are_assigned_by_the_server(
    client: TestClient, auth_headers: dict, exercise_ids: dict
) -> None:
    """Clients send sets in order; the server numbers them 1..n."""
    response = client.post(
        "/api/v1/workouts", json=build_payload(exercise_ids), headers=auth_headers
    )

    sets = response.json()["exercises"][0]["sets"]
    assert [s["set_number"] for s in sets] == [1, 2, 3]


def test_volume_is_computed_by_the_database(
    client: TestClient, auth_headers: dict, exercise_ids: dict
) -> None:
    """volume_kg is a generated column: weight x reps, never client-supplied."""
    response = client.post(
        "/api/v1/workouts", json=build_payload(exercise_ids), headers=auth_headers
    )

    working_set = response.json()["exercises"][0]["sets"][1]
    assert working_set["volume_kg"] == 60 * 5


def test_total_volume_excludes_warmups(
    client: TestClient, auth_headers: dict, exercise_ids: dict
) -> None:
    """The 40kg x 8 warmup (320kg) must not count toward the total."""
    response = client.post(
        "/api/v1/workouts", json=build_payload(exercise_ids), headers=auth_headers
    )

    expected = (60 * 5) + (60 * 5) + (90 * 5)
    assert response.json()["total_volume_kg"] == expected


def test_workout_order_is_preserved(
    client: TestClient, auth_headers: dict, exercise_ids: dict
) -> None:
    response = client.post(
        "/api/v1/workouts", json=build_payload(exercise_ids), headers=auth_headers
    )

    exercises = response.json()["exercises"]
    assert exercises[0]["exercise_name"] == "Overhead Press"
    assert exercises[1]["exercise_name"] == "Barbell Bench Press"
    assert [e["order_index"] for e in exercises] == [0, 1]


def test_same_exercise_twice_stays_two_blocks(
    client: TestClient, auth_headers: dict, exercise_ids: dict
) -> None:
    """The reason workout_exercises exists at all.

    Bench at the start and bench again at the end must remain two
    distinct blocks, not collapse into one pile of sets.
    """
    bench = exercise_ids["Barbell Bench Press"]
    payload = {
        "performed_on": "2026-07-28",
        "exercises": [
            {"exercise_id": bench, "sets": [{"weight_kg": 90, "reps": 5}]},
            {"exercise_id": bench, "sets": [{"weight_kg": 60, "reps": 15}]},
        ],
    }

    response = client.post("/api/v1/workouts", json=payload, headers=auth_headers)

    assert response.status_code == 201
    exercises = response.json()["exercises"]
    assert len(exercises) == 2
    assert exercises[0]["id"] != exercises[1]["id"]


def test_create_requires_authentication(
    client: TestClient, exercise_ids: dict
) -> None:
    response = client.post("/api/v1/workouts", json=build_payload(exercise_ids))

    assert response.status_code == 401


def test_create_rejects_zero_reps(
    client: TestClient, auth_headers: dict, exercise_ids: dict
) -> None:
    payload = build_payload(exercise_ids)
    payload["exercises"][0]["sets"][0]["reps"] = 0

    response = client.post("/api/v1/workouts", json=payload, headers=auth_headers)

    assert response.status_code == 422


def test_create_rejects_workout_with_no_exercises(
    client: TestClient, auth_headers: dict
) -> None:
    response = client.post(
        "/api/v1/workouts",
        json={"performed_on": "2026-07-28", "exercises": []},
        headers=auth_headers,
    )

    assert response.status_code == 422


def test_create_rejects_unknown_exercise(
    client: TestClient, auth_headers: dict
) -> None:
    payload = {
        "performed_on": "2026-07-28",
        "exercises": [{"exercise_id": 999999, "sets": [{"weight_kg": 50, "reps": 5}]}],
    }

    response = client.post("/api/v1/workouts", json=payload, headers=auth_headers)

    assert response.status_code == 400


def test_failed_workout_saves_nothing(
    client: TestClient, auth_headers: dict, exercise_ids: dict
) -> None:
    """THE TRANSACTION TEST.

    A payload whose SECOND exercise is invalid. The first is fine, so a
    naive implementation would insert the workout, insert exercise one,
    then fail -- leaving a half-saved session behind.

    Nothing at all should be stored.
    """
    payload = {
        "performed_on": "2026-07-28",
        "exercises": [
            {
                "exercise_id": exercise_ids["Overhead Press"],
                "sets": [{"weight_kg": 60, "reps": 5}],
            },
            {"exercise_id": 999999, "sets": [{"weight_kg": 60, "reps": 5}]},
        ],
    }

    response = client.post("/api/v1/workouts", json=payload, headers=auth_headers)
    assert response.status_code == 400

    listing = client.get("/api/v1/workouts", headers=auth_headers)
    assert listing.json() == []


def test_list_returns_summaries_newest_first(
    client: TestClient, auth_headers: dict, exercise_ids: dict
) -> None:
    older = build_payload(exercise_ids)
    older["performed_on"] = "2026-07-01"
    newer = build_payload(exercise_ids)
    newer["performed_on"] = "2026-07-20"

    client.post("/api/v1/workouts", json=older, headers=auth_headers)
    client.post("/api/v1/workouts", json=newer, headers=auth_headers)

    body = client.get("/api/v1/workouts", headers=auth_headers).json()

    assert [w["performed_on"] for w in body] == ["2026-07-20", "2026-07-01"]
    # set_count counts warmups; total_volume_kg does not. That is the
    # FILTER (WHERE NOT is_warmup) clause doing its job.
    assert body[0]["set_count"] == 4
    assert body[0]["exercise_count"] == 2


def test_get_detail_returns_full_workout(
    client: TestClient, auth_headers: dict, exercise_ids: dict
) -> None:
    created = client.post(
        "/api/v1/workouts", json=build_payload(exercise_ids), headers=auth_headers
    ).json()

    response = client.get(f"/api/v1/workouts/{created['id']}", headers=auth_headers)

    assert response.status_code == 200
    assert response.json()["id"] == created["id"]


def test_cannot_read_another_users_workout(
    client: TestClient, auth_headers: dict, exercise_ids: dict
) -> None:
    """THE ACCESS CONTROL TEST -- the most important one in this file.

    A second user must not be able to read the first user's workout,
    even knowing its exact id. 404 rather than 403, because 403 would
    confirm the workout exists.
    """
    created = client.post(
        "/api/v1/workouts", json=build_payload(exercise_ids), headers=auth_headers
    ).json()

    client.post(
        "/api/v1/auth/register",
        json={
            "email": "intruder@example.com",
            "password": "intruder-password",
            "display_name": "Intruder",
        },
    )
    token = client.post(
        "/api/v1/auth/login",
        data={"username": "intruder@example.com", "password": "intruder-password"},
    ).json()["access_token"]

    response = client.get(
        f"/api/v1/workouts/{created['id']}",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 404


def test_delete_removes_workout_and_its_sets(
    client: TestClient, auth_headers: dict, exercise_ids: dict
) -> None:
    """ON DELETE CASCADE cleaning up children automatically."""
    from sqlalchemy import text

    from app.db import engine

    created = client.post(
        "/api/v1/workouts", json=build_payload(exercise_ids), headers=auth_headers
    ).json()

    response = client.delete(f"/api/v1/workouts/{created['id']}", headers=auth_headers)
    assert response.status_code == 204

    with engine.connect() as conn:
        remaining_sets = conn.execute(text("SELECT COUNT(*) FROM sets;")).scalar_one()

    assert remaining_sets == 0


def test_delete_nonexistent_workout_returns_404(
    client: TestClient, auth_headers: dict
) -> None:
    response = client.delete("/api/v1/workouts/999999", headers=auth_headers)

    assert response.status_code == 404


def test_volume_endpoint_scopes_to_current_user(
    client: TestClient, auth_headers: dict, exercise_ids: dict
) -> None:
    ohp = exercise_ids["Overhead Press"]
    client.post("/api/v1/workouts", json=build_payload(exercise_ids), headers=auth_headers)

    mine = client.get(f"/api/v1/exercises/{ohp}/volume?weeks=52", headers=auth_headers)
    assert mine.status_code == 200
    # Warmups excluded: only the two 60x5 working sets count.
    assert mine.json()[0]["session_volume"] == 600

    client.post(
        "/api/v1/auth/register",
        json={
            "email": "other@example.com",
            "password": "other-password",
            "display_name": "Other",
        },
    )
    token = client.post(
        "/api/v1/auth/login",
        data={"username": "other@example.com", "password": "other-password"},
    ).json()["access_token"]

    theirs = client.get(
        f"/api/v1/exercises/{ohp}/volume?weeks=52",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert theirs.status_code == 404


def test_health_check_reports_database_reachable(client: TestClient) -> None:
    response = client.get("/api/v1/health")

    assert response.status_code == 200
    assert response.json()["database"] == "reachable"
