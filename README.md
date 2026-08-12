# LiftSync

[![CI](https://github.com/DilpreetMann25/LiftSync/actions/workflows/ci.yml/badge.svg)](https://github.com/DilpreetMann25/LiftSync/actions/workflows/ci.yml)

AI-driven strength and nutrition tracking. Logs training, correlates macronutrient intake with lifting performance, and uses an LLM agent that queries the database directly to diagnose plateaus and generate corrective programming blocks.

Built as a portfolio project demonstrating relational schema design, REST API development, agentic AI integration, and cloud deployment.

---

## Stack

| Layer | Technology |
| --- | --- |
| Database | PostgreSQL 16, Alembic migrations |
| Backend | Python 3.12, FastAPI, SQLAlchemy Core, Pydantic v2 |
| Auth | JWT (PyJWT), bcrypt password hashing |
| Frontend | React, Tailwind CSS *(planned)* |
| AI | Anthropic / OpenAI tool-calling agent *(planned)* |
| Infrastructure | Docker Compose locally; AWS EC2 + RDS *(planned)* |
| CI/CD | GitHub Actions *(planned)* |

---

## Running it locally

**Prerequisites:** Docker Desktop, Python 3.11+

```bash
git clone git@github.com:DilpreetMann25/LiftSync.git
cd LiftSync
cp .env.example .env
```

Generate a signing key and paste it into `.env` as `JWT_SECRET_KEY`:

```bash
python3 -c "import secrets; print(secrets.token_urlsafe(48))"
```

Start the database:

```bash
docker compose up -d
until docker compose exec -T db pg_isready -U liftsync -q; do sleep 1; done
```

Set up the backend, apply migrations, and seed demo data:

```bash
cd backend
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

alembic upgrade head
python scripts/seed_dev_data.py

uvicorn app.main:app --reload
```

Open **http://localhost:8000/docs**.

### Demo account

```
username: demo@liftsync.app
password: liftsync-demo-2026
```

Seeded with 8 weeks of training data containing a deliberate overhead press plateau — weight frozen at 60kg for the final three weeks while bench and squat continue progressing. This is the scenario the AI coach is built to diagnose.

Click **Authorize** in `/docs`, then try `GET /api/v1/analytics/plateaus` — the overhead press should be flagged.

To use the AI coach, add a free [Google AI Studio](https://aistudio.google.com) key to `.env` as `GEMINI_API_KEY`, then `POST /api/v1/coach/ask` with:

```json
{"question": "I'm plateauing on my overhead press at 60kg. What should I do?"}
```

Everything else works without a key.

---

## The AI coach

`POST /api/v1/coach/ask` is the feature the rest of the project exists to support. It is a **tool-calling agent**, not a prompt with data pasted into it.

The model receives a set of function descriptions and decides for itself what to investigate. Asked *"I'm plateauing on my overhead press at 60kg"*, it ran seven tool calls unprompted:

```
detect_plateaus          → is the claim actually true?
exercise_progression     → how has it been trending?
muscle_group_volume ×2   → front delts, then triceps
bodyweight_trend         → gaining or cutting?
nutrition_summary        → eating enough to recover?
list_available_exercises → what can I prescribe?
```

It confirmed the plateau before accepting the premise, ruled out a caloric deficit, surfaced a weekend protein drop nobody asked about (184g weekdays vs 128g weekends), and produced a four-week block using only movements in the user's exercise library.

**Design decisions worth noting:**

**The model never executes anything.** It emits a request; `app/agent.py` decides whether to honour it. Every tool receives `conn` and `user_id` as its first arguments, supplied by application code — so no argument the model could produce would read another user's data.

**Tool errors are returned as data, not raised.** An unknown exercise yields `{"error": "No exercise named 'Military Press'. Call list_available_exercises."}`, letting the model correct itself. An exception would abandon the investigation over a recoverable mistake.

**Output is schema-enforced.** `CoachProgram.model_json_schema()` is sent as the required response shape and the reply is validated before storage. Malformed output is a 502, not a corrupt record.

**Every run is auditable.** `ai_programs` stores the prompt, the tools called, the exact data the model saw, the generated block, and token counts — so "why did it say that?" is always answerable.

**The provider is abstracted.** `app/llm.py` is the only file that knows the vendor. When Google replaced `generateContent` with the Interactions API mid-build, the rewrite touched that one file; the agent logic was untouched. The same seam lets the entire test suite run against a scripted `FakeProvider` with no API key and no cost.

---

## Schema design notes

The interesting decisions, and why:

**`workout_exercises` sits between workouts and sets.** Linking sets directly to `(workout_id, exercise_id)` loses information: bench pressed at the start of a session and again as a burnout at the end collapse into one indistinguishable block. The intermediate table carries `order_index` and `superset_group`, preserving session structure.

**There is no `workouts.focus_area` column.** Focus area is derivable from the muscle groups of the exercises performed. A stored copy can contradict the underlying sets; a derived value cannot.

**Muscle involvement is weighted, not boolean.** `exercise_muscle_groups.contribution` is a `NUMERIC(3,2)` from 0 to 1 — bench press contributes 1.00 to chest, 0.40 to front delts, 0.50 to triceps. A boolean `is_primary` would make bench count either fully or not at all toward shoulder volume; both answers are wrong.

**All weights stored in kilograms as `NUMERIC`.** Unit conversion is a presentation concern. `FLOAT` cannot represent 82.5 exactly and the error compounds under `SUM()`.

**`sets.volume_kg` is a generated column.** Postgres computes `weight_kg * reps` on write. Volume appears in nearly every analytics query; computing it once beats recomputing it on every read.

**Reference data lives in migrations; fake data does not.** Muscle groups, exercises, and food items ship to every environment because the app cannot function without them. The 8 weeks of demo training data is a standalone script that must never run in production.

### Known issues

- Bodyweight exercises log 0kg added load, so `weight × reps` yields zero volume. Pull-ups currently contribute nothing to lat volume. Needs resolving by incorporating logged bodyweight into the load calculation.

---

## Project status

| Phase | Status |
| --- | --- |
| 1 — Database design, migrations, seed data | Complete |
| 2 — Backend API, auth, CRUD | Complete |
| 3 — Analytics layer (e1RM, plateau detection) | Complete |
| 4 — React frontend | Not started |
| 5 — Autonomous AI coach | Complete |
| 6 — AWS deployment (EC2 + RDS) | Not started |
| 7 — CI/CD and polish | CI complete |

57 tests, no network calls, running on every push.

Detailed roadmap: [`docs/ROADMAP.md`](docs/ROADMAP.md)

---

## Repository layout

```
LiftSync/
├── docker-compose.yml          Local Postgres
├── docs/ROADMAP.md             Build plan
└── backend/
    ├── app/
    │   ├── main.py             FastAPI entry point
    │   ├── config.py           Environment configuration
    │   ├── db.py               Connection pooling
    │   ├── security.py         Password hashing, JWT
    │   ├── dependencies.py     get_current_user
    │   ├── schemas.py          Pydantic request/response models
    │   └── routers/            Endpoint groups
    ├── alembic/versions/       Versioned migrations
    └── scripts/                Development utilities
```
