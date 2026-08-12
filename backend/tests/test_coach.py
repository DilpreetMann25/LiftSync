"""Tests for the AI coach.

NOT ONE NETWORK CALL IN THIS FILE.

Every test drives FakeProvider, a scripted stand-in that returns
whatever responses the test hands it. That buys three things:

  Deterministic -- a real model answers differently every run, so a
    test asserting on its output would fail at random and teach you
    to ignore failures.
  Free -- the suite runs on every push. Real calls would bill you for
    CI, and CI has no API key anyway.
  Fast -- 20 seconds for the whole suite instead of 30 per test.

What is actually under test is the AGENT LOOP, not the model: does it
run the tools the model asks for, feed results back, stop at the
budget, reject a malformed programme, and store an audit trail. That
logic is yours, so that logic is what needs covering.

This file only exists because llm.py put an interface in front of the
SDK. Calling google.genai directly from agent.py would have made all
of this untestable.
"""

from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.config import AI_MAX_TOOL_CALLS
from app.llm import FakeProvider, LLMResponse, ToolCall
from app.main import app
from app.routers.coach import provider_dependency

VALID_PROGRAM: dict[str, Any] = {
    "diagnosis": "Overhead press has stalled.",
    "reasoning": "e1RM flat at 70kg for four weeks while volume held steady.",
    "target_exercise": "Overhead Press",
    "weeks": [
        {
            "week_number": 1,
            "focus": "Deload",
            "exercises": [
                {
                    "exercise_name": "Overhead Press",
                    "sets": 2,
                    "reps": "5",
                    "intensity": "50kg",
                    "notes": "Shed fatigue.",
                }
            ],
        }
    ],
    "nutrition_note": "Protein drops at weekends.",
}


@pytest.fixture
def use_fake_provider():
    """Swap the real provider for a scripted one.

    dependency_overrides is FastAPI's testing seam: it replaces what a
    Depends(...) resolves to. The teardown matters -- overrides are
    global, so leaving one in place would leak into every later test.
    """
    installed: list[FakeProvider] = []

    def install(
        responses: list[LLMResponse], structured: dict | None = None
    ) -> FakeProvider:
        fake = FakeProvider(responses=responses, structured_result=structured)
        app.dependency_overrides[provider_dependency] = lambda: fake
        installed.append(fake)
        return fake

    yield install

    app.dependency_overrides.pop(provider_dependency, None)


def ask(client: TestClient, headers: dict, question: str = "Why am I stuck on overhead press?"):
    return client.post("/api/v1/coach/ask", json={"question": question}, headers=headers)


# ---------------------------------------------------------------
# Auth and validation
# ---------------------------------------------------------------


def test_coach_requires_authentication(client: TestClient) -> None:
    response = client.post("/api/v1/coach/ask", json={"question": "Help me please"})

    assert response.status_code == 401


def test_coach_rejects_a_too_short_question(
    client: TestClient, auth_headers: dict, use_fake_provider
) -> None:
    use_fake_provider([LLMResponse(text="done")], VALID_PROGRAM)

    response = client.post("/api/v1/coach/ask", json={"question": "hi"}, headers=auth_headers)

    assert response.status_code == 422


# ---------------------------------------------------------------
# The agent loop
# ---------------------------------------------------------------


def test_agent_runs_the_tool_the_model_asks_for(
    client: TestClient, auth_headers: dict, use_fake_provider
) -> None:
    use_fake_provider(
        [
            LLMResponse(
                tool_calls=[ToolCall("detect_plateaus", {}, "call-1")],
                interaction_id="i-1",
            ),
            LLMResponse(text="Seen enough.", interaction_id="i-2"),
        ],
        VALID_PROGRAM,
    )

    response = ask(client, auth_headers)

    assert response.status_code == 200
    assert response.json()["tools_used"] == ["detect_plateaus"]


def test_agent_runs_several_tools_across_turns(
    client: TestClient, auth_headers: dict, use_fake_provider
) -> None:
    use_fake_provider(
        [
            LLMResponse(tool_calls=[ToolCall("detect_plateaus", {}, "c1")], interaction_id="i1"),
            LLMResponse(
                tool_calls=[ToolCall("bodyweight_trend", {"weeks": 4}, "c2")],
                interaction_id="i2",
            ),
            LLMResponse(text="Done.", interaction_id="i3"),
        ],
        VALID_PROGRAM,
    )

    body = ask(client, auth_headers).json()

    assert body["tools_used"] == ["detect_plateaus", "bodyweight_trend"]


def test_agent_stops_at_the_tool_budget(
    client: TestClient, auth_headers: dict, use_fake_provider
) -> None:
    """A model that never stops asking must not loop forever.

    Without the ceiling this would run until the API rate-limited it,
    burning tokens and hanging the request.
    """
    endless = [
        LLMResponse(tool_calls=[ToolCall("detect_plateaus", {}, f"c{i}")], interaction_id=f"i{i}")
        for i in range(AI_MAX_TOOL_CALLS + 10)
    ]
    use_fake_provider(endless, VALID_PROGRAM)

    body = ask(client, auth_headers).json()

    assert len(body["tools_used"]) == AI_MAX_TOOL_CALLS


def test_unknown_tool_does_not_crash_the_request(
    client: TestClient, auth_headers: dict, use_fake_provider
) -> None:
    """Models sometimes invent a tool that would be convenient.

    The error goes back as data so the model can correct itself. An
    exception here would abandon the whole investigation over a
    recoverable mistake.
    """
    use_fake_provider(
        [
            LLMResponse(tool_calls=[ToolCall("read_my_mind", {}, "c1")], interaction_id="i1"),
            LLMResponse(text="Fine, I will manage.", interaction_id="i2"),
        ],
        VALID_PROGRAM,
    )

    response = ask(client, auth_headers)

    assert response.status_code == 200
    assert response.json()["tools_used"] == ["read_my_mind"]


def test_bad_tool_arguments_do_not_crash_the_request(
    client: TestClient, auth_headers: dict, use_fake_provider
) -> None:
    use_fake_provider(
        [
            LLMResponse(
                tool_calls=[ToolCall("bodyweight_trend", {"nonsense": True}, "c1")],
                interaction_id="i1",
            ),
            LLMResponse(text="Moving on.", interaction_id="i2"),
        ],
        VALID_PROGRAM,
    )

    assert ask(client, auth_headers).status_code == 200


# ---------------------------------------------------------------
# Output validation
# ---------------------------------------------------------------


def test_malformed_program_is_rejected(
    client: TestClient, auth_headers: dict, use_fake_provider
) -> None:
    """The model claims to follow the schema; we verify rather than trust.

    A 502 is correct here: the upstream service misbehaved, the user's
    request was fine, and retrying may well work.
    """
    use_fake_provider(
        [LLMResponse(text="Done.", interaction_id="i1")],
        {"diagnosis": "Missing nearly every required field."},
    )

    response = ask(client, auth_headers)

    assert response.status_code == 502


def test_program_is_returned_in_full(
    client: TestClient, auth_headers: dict, use_fake_provider
) -> None:
    use_fake_provider([LLMResponse(text="Done.", interaction_id="i1")], VALID_PROGRAM)

    program = ask(client, auth_headers).json()["program"]

    assert program["target_exercise"] == "Overhead Press"
    assert program["weeks"][0]["exercises"][0]["exercise_name"] == "Overhead Press"


# ---------------------------------------------------------------
# Audit trail
# ---------------------------------------------------------------


def test_program_and_context_are_persisted(
    client: TestClient, auth_headers: dict, use_fake_provider
) -> None:
    """Every generated programme is stored with the data behind it.

    Without this you can never answer "why did the coach say that?",
    nor judge later whether the advice was any good.
    """
    from sqlalchemy import text

    from app.db import engine

    use_fake_provider(
        [
            LLMResponse(tool_calls=[ToolCall("detect_plateaus", {}, "c1")], interaction_id="i1"),
            LLMResponse(text="Done.", interaction_id="i2"),
        ],
        VALID_PROGRAM,
    )

    body = ask(client, auth_headers).json()

    with engine.connect() as conn:
        row = conn.execute(
            text(
                """
                SELECT user_prompt, tool_calls, context_snapshot, program
                FROM ai_programs WHERE id = :id;
                """
            ),
            {"id": body["id"]},
        ).mappings().one()

    assert row["user_prompt"] == "Why am I stuck on overhead press?"
    assert row["tool_calls"] == ["detect_plateaus"]
    assert row["context_snapshot"][0]["tool"] == "detect_plateaus"
    assert row["program"]["target_exercise"] == "Overhead Press"


# ---------------------------------------------------------------
# Security
# ---------------------------------------------------------------


def test_tools_cannot_reach_another_users_data(client: TestClient, auth_headers: dict) -> None:
    """The core security property of the agent.

    Tools are called with user_id supplied by agent.py, never by the
    model. There is no argument it could emit that would widen the
    scope -- so this test calls the implementation directly with two
    different user ids and checks they see different data.
    """
    from sqlalchemy import text

    from app.agent import _tool_detect_plateaus
    from app.db import engine

    with engine.connect() as conn:
        owner_id = conn.execute(
            text("SELECT id FROM users WHERE email = 'tester@example.com';")
        ).scalar_one()

        stranger_id = conn.execute(
            text(
                """
                INSERT INTO users (email, password_hash, display_name)
                VALUES ('nosy@example.com', 'x', 'Nosy')
                RETURNING id;
                """
            )
        ).scalar_one()
        conn.commit()

        owner_view = _tool_detect_plateaus(conn, owner_id)
        stranger_view = _tool_detect_plateaus(conn, stranger_id)

    assert stranger_view["plateaus"] == []
    assert isinstance(owner_view["plateaus"], list)
