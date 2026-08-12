"""LLM provider abstraction.

WHY A LAYER INSTEAD OF CALLING THE SDK DIRECTLY
-----------------------------------------------
This file just proved its own worth. It was written against Gemini's
generateContent API, which Google has since replaced with the
Interactions API -- different call, different response shape, different
conversation model. Rewriting it touched one file. agent.py, which
holds the actual coaching logic, did not change at all.

Three payoffs:

  1. Vendor and API changes are contained here.
  2. Tests run against FakeProvider -- no network, no key, no cost,
     deterministic. A suite that calls a real model is slow, flaky,
     and bills you for running it.
  3. agent.py stays readable, because vendor JSON wrangling lives here.

WHAT A "TOOL CALL" ACTUALLY IS
------------------------------
You send the model a list of function descriptions. Instead of
replying with text, it can reply with structured JSON: "call
exercise_progression with exercise_name='Overhead Press'".

The model cannot execute anything. It emits a request. YOUR code
decides whether to honour it, runs the function, and returns the
result. That boundary is the entire security model of an agent.

SERVER-SIDE STATE
-----------------
The Interactions API stores conversation history for you. Rather than
resending the whole transcript each turn, you pass
`previous_interaction_id` and the server stitches it together. Less
data over the wire, and no history bookkeeping in agent.py.

Note that only history persists -- `tools` and `system_instruction`
are per-interaction and must be re-sent every turn.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol

from app.config import AI_MODEL, GEMINI_API_KEY


@dataclass
class ToolCall:
    """A model's request to run one of your functions."""

    name: str
    arguments: dict[str, Any]
    # The API needs this echoed back so it can match a result to the
    # request that produced it -- necessary when several tools are
    # called in one turn.
    call_id: str | None = None


@dataclass
class ToolSpec:
    """A function description, in vendor-neutral form."""

    name: str
    description: str
    # JSON Schema for the parameters. The model reads this to decide
    # what to pass, so the wording here is prompt, not documentation.
    parameters: dict[str, Any]


@dataclass
class LLMResponse:
    """One turn from the model: tool requests, or final text."""

    text: str = ""
    tool_calls: list[ToolCall] = field(default_factory=list)
    # Handle for continuing this conversation server-side.
    interaction_id: str | None = None
    input_tokens: int = 0
    output_tokens: int = 0

    @property
    def wants_tools(self) -> bool:
        return bool(self.tool_calls)


class LLMProvider(Protocol):
    """The contract every provider implements.

    A Protocol is structural typing: any class with these methods
    satisfies it, no inheritance required.
    """

    def generate(
        self,
        system_prompt: str,
        user_input: Any,
        tools: list[ToolSpec],
        previous_interaction_id: str | None = None,
    ) -> LLMResponse: ...

    def generate_structured(
        self,
        system_prompt: str,
        prompt: str,
        json_schema: dict[str, Any],
    ) -> tuple[dict[str, Any], int, int]: ...


def _token_counts(interaction: Any) -> tuple[int, int]:
    """Read token usage defensively.

    The field has moved between SDK versions (usage vs usage_metadata,
    input_tokens vs prompt_token_count). Token counts are for display
    and cost tracking only -- worth reporting, never worth crashing a
    request over. Hence the fallbacks and the 0 default.
    """
    usage = getattr(interaction, "usage", None) or getattr(
        interaction, "usage_metadata", None
    )
    if usage is None:
        return 0, 0

    input_tokens = (
        getattr(usage, "total_input_tokens", None)
        or getattr(usage, "input_tokens", None)
        or getattr(usage, "prompt_token_count", None)
        or 0
    )
    output_tokens = (
        getattr(usage, "total_output_tokens", None)
        or getattr(usage, "output_tokens", None)
        or getattr(usage, "candidates_token_count", None)
        or 0
    )
    # Note: `total_thought_tokens` is billed but reported separately.
    # Gemini 3 spends tokens reasoning before it answers -- often more
    # than the visible reply costs. Worth knowing when estimating cost.
    return int(input_tokens), int(output_tokens)


# ===================================================================
# Gemini — Interactions API
# ===================================================================


class GeminiProvider:
    """Google Gemini via the Interactions API."""

    def __init__(self, model: str = AI_MODEL, api_key: str = GEMINI_API_KEY) -> None:
        if not api_key:
            raise RuntimeError("GEMINI_API_KEY is not set. See .env.example.")

        # Imported here rather than at module level so the app still
        # starts without the SDK installed when using FakeProvider.
        from google import genai

        self._client = genai.Client(api_key=api_key)
        self._model = model

    @staticmethod
    def _to_tool_dicts(tools: list[ToolSpec]) -> list[dict[str, Any]]:
        """ToolSpec -> the API's tool format. Near-identical by design."""
        return [
            {
                "type": "function",
                "name": tool.name,
                "description": tool.description,
                "parameters": tool.parameters,
            }
            for tool in tools
        ]

    def generate(
        self,
        system_prompt: str,
        user_input: Any,
        tools: list[ToolSpec],
        previous_interaction_id: str | None = None,
    ) -> LLMResponse:
        """One turn.

        `user_input` is a question on the first call, and a list of
        function_result objects on subsequent ones. The API accepts
        both, which is why this is a single method rather than two.
        """
        kwargs: dict[str, Any] = {
            "model": self._model,
            "system_instruction": system_prompt,
            "input": user_input,
            "tools": self._to_tool_dicts(tools),
        }
        # Tools and system_instruction are interaction-scoped and get
        # re-sent every turn; only history is remembered server-side.
        if previous_interaction_id:
            kwargs["previous_interaction_id"] = previous_interaction_id

        interaction = self._client.interactions.create(**kwargs)

        # A response is a list of STEPS, each with a type:
        #   "thought"       - the model's internal reasoning. Billed,
        #                     but opaque; we ignore it.
        #   "model_output"  - the visible reply, in .content
        #   "function_call" - a request to run one of our tools
        tool_calls: list[ToolCall] = []

        for step in interaction.steps or []:
            if getattr(step, "type", None) == "function_call":
                tool_calls.append(
                    ToolCall(
                        name=step.name,
                        arguments=dict(step.arguments or {}),
                        call_id=getattr(step, "id", None),
                    )
                )

        input_tokens, output_tokens = _token_counts(interaction)

        return LLMResponse(
            # output_text is a convenience the SDK provides: the text
            # from every model_output step, already concatenated.
            text=interaction.output_text or "",
            tool_calls=tool_calls,
            interaction_id=interaction.id,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
        )

    def generate_structured(
        self,
        system_prompt: str,
        prompt: str,
        json_schema: dict[str, Any],
    ) -> tuple[dict[str, Any], int, int]:
        """Force the reply into a given JSON shape.

        `response_format` makes the model emit JSON matching the
        schema. This is what turns "write me a programme" from prose
        you would parse with regex into an object you can validate and
        store.

        No tools on this call. Tool use and strict JSON pull against
        each other -- one needs the model free to emit function calls,
        the other forbids anything but schema-shaped output.
        """
        import json

        interaction = self._client.interactions.create(
            model=self._model,
            system_instruction=system_prompt,
            input=prompt,
            response_format=json_schema,
        )

        input_tokens, output_tokens = _token_counts(interaction)
        return json.loads(interaction.output_text), input_tokens, output_tokens


# ===================================================================
# Fake — for tests
# ===================================================================


class FakeProvider:
    """A scripted provider. No network, no key, no cost.

    Returns a queue of pre-written responses, so tests can assert on
    the agent's BEHAVIOUR -- which tools it called, in what order,
    whether it stopped correctly -- without any of that depending on
    what a real model feels like doing today.

    Testing agent logic against a live model is a trap: the test fails
    intermittently and you can never tell whether your code broke or
    the model simply answered differently.
    """

    def __init__(
        self,
        responses: list[LLMResponse] | None = None,
        structured_result: dict[str, Any] | None = None,
    ) -> None:
        self._responses = list(responses or [LLMResponse(text="Looks fine to me.")])
        self._structured_result = structured_result or {}
        self.calls: list[dict[str, Any]] = []

    def generate(
        self,
        system_prompt: str,
        user_input: Any,
        tools: list[ToolSpec],
        previous_interaction_id: str | None = None,
    ) -> LLMResponse:
        self.calls.append(
            {"input": user_input, "tools": [t.name for t in tools]}
        )
        if self._responses:
            return self._responses.pop(0)
        return LLMResponse(text="No further questions.")

    def generate_structured(
        self,
        system_prompt: str,
        prompt: str,
        json_schema: dict[str, Any],
    ) -> tuple[dict[str, Any], int, int]:
        self.calls.append({"structured_prompt": prompt})
        return self._structured_result, 0, 0


def get_provider() -> LLMProvider:
    """Build the provider named in configuration."""
    from app.config import LLM_PROVIDER

    if LLM_PROVIDER == "fake":
        return FakeProvider()
    if LLM_PROVIDER == "gemini":
        return GeminiProvider()
    raise RuntimeError(f"Unknown LLM_PROVIDER: {LLM_PROVIDER!r}")
