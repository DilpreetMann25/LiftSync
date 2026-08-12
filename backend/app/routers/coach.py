"""The AI coach endpoint."""

import logging

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import ValidationError
from sqlalchemy.engine import Connection

from app.agent import run_coach
from app.db import get_connection
from app.dependencies import get_current_user
from app.llm import get_provider
from app.schemas import CoachQuestion, CoachResponse

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/coach", tags=["coach"])


@router.post("/ask", response_model=CoachResponse)
def ask_coach(
    payload: CoachQuestion,
    conn: Connection = Depends(get_connection),
    current_user: dict = Depends(get_current_user),
) -> dict:
    """Ask the coach a question about your training.

    The agent decides for itself which of your data to look at, then
    returns a structured 4-week block along with the tools it used to
    reach that conclusion.

    Slow by design — several model round-trips, typically 10-30
    seconds. That is the cost of letting it investigate rather than
    guess.
    """
    try:
        provider = get_provider()
    except RuntimeError as exc:
        # Missing API key or bad config. 503, not 500: the service is
        # unavailable, the request was not wrong.
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"AI coach is not configured: {exc}",
        ) from exc

    try:
        return run_coach(conn, current_user["id"], payload.question, provider)

    except ValidationError as exc:
        # The model returned JSON that did not match CoachProgram.
        # Worth distinguishing from a generic failure: this one is
        # retryable, and it means the schema or prompt needs work.
        logger.warning("Coach returned malformed program: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="The coach returned a malformed program. Try asking again.",
        ) from exc

    except Exception as exc:
        conn.rollback()
        # Log the detail, return something generic. Upstream errors can
        # contain API keys or internal paths, and those must not reach
        # a client.
        logger.exception("Coach request failed")
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="The coach is unavailable right now. Try again shortly.",
        ) from exc
