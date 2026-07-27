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

# --- Auth ------------------------------------------------------
# This key signs every access token. Anyone holding it can forge a
# token for any user, so it is the single most sensitive value in the
# app. In production it comes from AWS Secrets Manager, never a file.
JWT_SECRET_KEY = os.getenv("JWT_SECRET_KEY", "")
JWT_ALGORITHM = os.getenv("JWT_ALGORITHM", "HS256")
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "60"))

if not JWT_SECRET_KEY:
    raise RuntimeError("JWT_SECRET_KEY is not set. See .env.example.")

# Refuse to boot in production with the placeholder value. A check
# like this costs nothing and prevents a genuinely catastrophic
# deployment mistake.
if ENVIRONMENT != "development" and JWT_SECRET_KEY == "changeme":
    raise RuntimeError("JWT_SECRET_KEY is still the placeholder. Generate a real one.")

# Which web origins may call this API from a browser. Empty in
# production would block your own frontend, so it is explicit.
CORS_ORIGINS = [
    origin.strip()
    for origin in os.getenv("CORS_ORIGINS", "http://localhost:5173").split(",")
    if origin.strip()
]
