# LiftSync — Build Roadmap

**Stack (locked):** React + Tailwind · Python/FastAPI · PostgreSQL · AWS (EC2 + RDS) · OpenAI or Anthropic API · GitHub Actions

**Level:** Comfortable coding, new to cloud/DB
**Mode:** Mixed by layer — scaffolding (config, infra, boilerplate) is provided; schema design, business logic, SQL, and the AI agent are written by hand.

---

## Ground rules

1. **Never paste code you can't explain.** If you can't say why line 12 exists, ask. An interviewer will.
2. **Every phase ends with a checkpoint** — a task completed unaided. That's the retention test.
3. **Local-first.** Docker Postgres through Phase 5. AWS does not appear until Phase 6.
4. **Migrations from commit one.** No manually-created tables, ever. This is the biggest habit gap between hobby projects and enterprise work.
5. **Commit small and often.** Git history is part of the portfolio.

---

## Phase 0 — Foundations & Local Environment
**~Week 1 · scaffolded**

- Monorepo structure: `/backend`, `/frontend`, `/infra`, `/docs`
- Python virtualenv, dependency management
- `docker-compose.yml` running Postgres 16 locally ✅
- `.env` handling and `.gitignore` hygiene — secrets never touch Git
- pgAdmin or DBeaver connected to local DB

**Learn:** what a container actually is, connection strings, why config lives in env vars.
**Checkpoint:** connect to local Postgres from a terminal, create and drop a table by hand.

---

## Phase 1 — Database Design ⭐
**COMPLETE**

The load-bearing phase. A weak schema poisons everything downstream, and it's what interviewers probe hardest.

- [x] Design `users`, `workouts`, `exercises`, `sets`, `nutrition_logs`, `bodyweight_logs`
- [x] Primary keys, foreign keys, `ON DELETE` behaviour, `CHECK` constraints
- [x] Correct types: `NUMERIC` not `FLOAT`; `DATE` vs `TIMESTAMPTZ`
- [x] Indexes — composite `(user_id, date)` on log tables
- [x] Seed data: 15 muscle groups, 15 exercises, weighted muscle mappings
- [x] Alembic wired up — migrations `0001` schema, `0002` exercises, `0003` food items
- [x] `seed_dev_data.py` — 8 weeks of training data with a deliberate OHP plateau
- [x] **Checkpoint passed:** raw SQL surfacing the plateau (60kg × 9 sessions)

**Learned:** normalization to 3NF, partial unique indexes, generated columns, `GROUP BY` semantics, multi-table `JOIN`s and row multiplication, migrations vs. seed scripts.

### Key design decisions made

| Decision | Rationale |
|---|---|
| No `workouts.focus_area` | Derivable from exercises performed; stored copies drift from the truth |
| No `users.current_bodyweight` | Same reason — read the latest `bodyweight_logs` row |
| `workout_exercises` join table | Lets one exercise appear twice in a session as distinct blocks; carries `superset_group` |
| Weighted `contribution` (0–1) | Bench press counts partially toward shoulder volume; a boolean would be wrong both ways |
| All weights in kg | Unit conversion is presentation, never storage |
| `NUMERIC` over `FLOAT` | Floats can't represent 82.5 exactly; error compounds in `SUM()` |
| `sets.volume_kg` generated | Computed once on write, not on every analytics read |
| Reference data in migrations, fake data in a script | Muscle groups ship to production; demo lifters must not |

### Known open issue

**Bodyweight exercises compute to zero volume.** Pull-ups are logged at 0kg added load, so `weight × reps` = 0 and they contribute nothing to lat volume. Needs resolving in Phase 3 — likely by adding the user's logged bodyweight to the load.

---

## Phase 2 — Backend API
**~Week 2–4 · skeleton scaffolded, endpoints written by hand**

- FastAPI layout: routers, services, repositories
- SQLAlchemy 2.0 models mapped to the schema
- Pydantic request/response schemas (validation at the boundary)
- Auth: registration, bcrypt hashing, JWT access tokens
- Full CRUD: workouts, sets, nutrition, bodyweight
- pytest against a throwaway test database

**Learn:** dependency injection, request lifecycle, the N+1 query problem, pagination, never trusting client input.
**Checkpoint:** explain what happens between the HTTP request arriving and the row hitting Postgres.

---

## Phase 3 — Analytics Layer
**~Week 4–5 · written by hand**

What makes this a fitness *intelligence* app rather than a form with a database.

- Session volume (Σ sets × reps × weight)
- Estimated 1RM (Epley / Brzycki)
- Progressive overload trajectory per lift — rolling 4-week slope
- **Plateau detection**: defined numerically (e1RM slope ≈ 0 across ≥3 weeks)
- Macro-to-performance correlation: bodyweight + protein vs. strength output

**Learn:** SQL **window functions** (`LAG`, `AVG OVER`, `ROW_NUMBER`). The most differentiating skill in this project — most junior candidates can't write one.
**Checkpoint:** 4-week rolling-average volume query using only window functions.

---

## Phase 4 — Frontend
**~Week 5–6**

- React + Vite + Tailwind
- Fast workout logging UI — must be usable one-handed between sets
- Nutrition and bodyweight entry
- Recharts: volume over time, e1RM progression, bodyweight vs. strength overlay
- Auth flow and token storage

**Learn:** component state, data fetching, loading/error states, how API shape drives UI complexity.

---

## Phase 5 — The Autonomous AI Coach ⭐⭐
**~Week 6–8 · the centerpiece, written by hand**

Critical distinction: this is **not** "stuff data into a prompt." A real agent decides *which* data it needs and fetches it via tool calls.

- Tools the LLM can invoke: `get_lift_history(exercise, weeks)`, `get_nutrition_summary(days)`, `get_bodyweight_trend(weeks)`, `get_volume_by_muscle_group(...)`
- Agent loop: prompt → model requests tools → backend queries Postgres → results returned → model reasons → final output
- **Structured output**: the 4-week block defined as a Pydantic model, enforced via JSON schema — always parseable, never prose to regex
- Persist to `ai_programs` with `tool_calls` and `context_snapshot` so results can be evaluated later
- Guardrails: token budget caps, prompt-injection defense, timeouts, graceful degradation

**Learn:** tool/function calling, context window management, cost per request, deterministic output enforcement.
**Checkpoint:** trace one full request — "I'm plateauing on OHP at 135lbs" — naming every tool call, SQL query, and token cost.

---

## Phase 6 — AWS Deployment
**~Week 8–10**

The part most portfolio projects skip.

- **VPC**: public subnet (EC2) + private subnet (RDS). RDS must **never** be publicly reachable.
- **RDS**: Postgres instance, parameter groups, automated backups
- **EC2**: Ubuntu, Nginx reverse proxy, systemd service, HTTPS via Let's Encrypt
- Security groups as firewall rules — the EC2 SG is the only thing allowed into the RDS SG on 5432
- **IAM roles, not access keys.** Secrets in AWS Secrets Manager or SSM Parameter Store.
- Run Alembic migrations against RDS

**Learn:** VPC/subnet/routing, least privilege, why "works locally" ≠ "works deployed."

> ⚠️ **Set an AWS billing alarm at $5 on day one of this phase.** Free tier covers most of it, but an oversized RDS instance left running is the classic $200 surprise.

---

## Phase 7 — CI/CD & Portfolio Polish
**~Week 10–12**

- GitHub Actions: lint → pytest → build → deploy to EC2 on merge to `main`
- Branch protection, PR-based workflow (even solo — it demonstrates process)
- Architecture diagram, thorough README, seeded demo account, 2-minute demo video
- Write up 3–4 real technical decisions and their tradeoffs — this becomes the interview script

---

## What separates this from a tutorial project

| Tutorial project | LiftSync |
|---|---|
| Tables created by hand | Versioned Alembic migrations |
| `SELECT *` everywhere | Window functions, indexed queries |
| Prompt stuffed with data | Agent with tool calling + structured output |
| Deployed to a free tier | VPC, private RDS, IAM roles, CI/CD |
| "It works" | Tests, guardrails, error handling, cost controls |
