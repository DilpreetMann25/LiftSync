"""Database connection handling.

WHY A POOL
----------
Opening a Postgres connection takes real time -- TCP handshake,
authentication, session setup. Doing that on every HTTP request would
make your API slow and would exhaust the database's connection limit
under load.

So SQLAlchemy keeps a POOL of open connections. A request borrows one,
uses it, and returns it. `create_engine` builds that pool once at
startup; it is not a connection itself.
"""

from collections.abc import Iterator

from sqlalchemy import create_engine
from sqlalchemy.engine import Connection

from app.config import DATABASE_URL

engine = create_engine(
    DATABASE_URL,
    # Send a cheap "are you alive?" before handing out a pooled
    # connection. Without this, a connection idle through an RDS
    # failover comes back dead and the request fails for no visible
    # reason. Costs a fraction of a millisecond.
    pool_pre_ping=True,
    pool_size=5,
    max_overflow=10,
)


def get_connection() -> Iterator[Connection]:
    """FastAPI dependency: hand a connection to a route, then clean up.

    The `yield` is what makes this work. Everything before it runs
    BEFORE your route function; everything after runs AFTER the
    response is sent -- even if the route raised an exception. That is
    how the connection always makes it back to the pool.
    """
    with engine.connect() as connection:
        yield connection
