"""Application configuration, read from environment variables.

Every setting the app needs is loaded here, in one place, from .env.
Nothing else in the codebase calls os.getenv -- so there is exactly
one file to look at when you need to know what this app requires to
start, and exactly one thing to change when deploying to AWS.
"""

import os
from pathlib import Path

from dotenv import load_dotenv

REPO_ROOT = Path(__file__).resolve().parents[2]
load_dotenv(REPO_ROOT / ".env")

DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    raise RuntimeError("DATABASE_URL is not set. Copy .env.example to .env.")

ENVIRONMENT = os.getenv("ENVIRONMENT", "development")

# Which web origins may call this API from a browser. Empty in
# production would block your own frontend, so it is explicit.
CORS_ORIGINS = [
    origin.strip()
    for origin in os.getenv("CORS_ORIGINS", "http://localhost:5173").split(",")
    if origin.strip()
]
