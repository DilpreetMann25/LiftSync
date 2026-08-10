"""LiftSync API — application entry point.

Run it:
    cd backend
    source .venv/bin/activate
    uvicorn app.main:app --reload

Then open http://localhost:8000/docs
"""

from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text
from sqlalchemy.engine import Connection

from app.config import CORS_ORIGINS, ENVIRONMENT
from app.db import get_connection
from app.routers import analytics, auth, exercises, workouts

app = FastAPI(
    title="LiftSync API",
    description="AI-driven strength and nutrition tracking.",
    version="0.1.0",
)

# Browsers block a page on one origin from calling an API on another
# unless the API explicitly permits it. Your React dev server will run
# on :5173 and this API on :8000 -- different origins -- so without
# this your frontend requests fail with an opaque CORS error.
app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Each router is a group of related endpoints living in its own file.
app.include_router(auth.router)
app.include_router(exercises.router)
app.include_router(workouts.router)
app.include_router(analytics.router)


@app.get("/api/v1/health", tags=["system"])
def health(conn: Connection = Depends(get_connection)) -> dict:
    """Liveness check.

    Deliberately runs a real query rather than just returning "ok".
    An API that responds while its database is unreachable is worse
    than one that admits it is down -- this is the endpoint AWS will
    poll in Phase 6 to decide whether the server should receive
    traffic at all.

    `Depends(get_connection)` is FastAPI's dependency injection: it
    calls get_connection(), passes the result in as `conn`, and
    handles cleanup afterwards. You never open or close a connection
    by hand in a route.
    """
    conn.execute(text("SELECT 1"))
    return {"status": "ok", "database": "reachable", "environment": ENVIRONMENT}
