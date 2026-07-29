# Database Glossary

Every term used while building LiftSync, with a concrete example from this project. Written to be re-read — skim it when something's gone fuzzy.

---

## The big picture

**PostgreSQL** (or **Postgres**) — a program whose job is storing data and answering questions about it. It runs continuously, listens on a network port, and waits for queries. Like Chrome or Spotify: a program, not a file. Alternatives include MySQL, SQLite, and SQL Server.

**Database** — the collection of data Postgres manages. One Postgres *server* can hold several databases, isolated from each other. Ours is named `liftsync`.

**Schema** — **two meanings, and this trips everyone up:**

1. *Informal, how we've mostly used it:* the overall structure of your data — which tables exist, what columns they have, what rules apply. "Designing the schema" = deciding all of that. `schema.sql` = the file that built it.
2. *Formal, Postgres's own meaning:* a namespace inside a database, like a folder for tables. Every table you made lives in the default schema called `public`. That's why `\dt` shows `public | workouts`.

In conversation, meaning 1. In Postgres output, meaning 2.

**Table** — one kind of thing, stored as rows and columns. `workouts`, `sets`, `users`. Roughly a spreadsheet tab, but with enforced rules.

**Row** (or *record*) — one instance. One workout. One set. One user.

**Column** (or *field*) — one attribute every row has. `weight_kg`, `performed_on`, `email`.

**psql** — Postgres's command-line client. Your phone line into the database. `\dt` lists tables, `\d sets` describes one, `\q` quits.

**Query** — a question or instruction sent to the database, written in SQL.

**SQL** — *Structured Query Language.* The language databases speak. Postgres understands it; Python does not — to Python, your SQL is just a string it forwards along.

---

## Where it physically lives

**Container** — a lightweight isolated environment running one program. Postgres runs inside a container on your Mac, not on your Mac directly.

**Volume** — disk storage that outlives the container. Ours is `liftsync_pgdata`. Delete the container and your data survives; delete the volume (`docker compose down -v`) and it's gone.

**Port** — a numbered door on a machine. Postgres listens on `5432` inside the container; Docker publishes that as `5433` on your Mac. Hence `localhost:5433` in `DATABASE_URL`.

**Connection** — an open line between a program and the database. Authenticated, stateful, and not free to create.

**Connection pool** — a set of connections kept open and reused, so each HTTP request borrows one instead of opening its own. Set up in `app/db.py`. `pool_pre_ping=True` tests a connection before lending it out, so one that died while idle gets replaced instead of failing your request.

---

## Data types

The declared kind of value a column holds. Postgres rejects anything that doesn't fit.

| Type | Holds | Used in LiftSync |
| --- | --- | --- |
| `TEXT` | strings of any length | `email`, `display_name` |
| `SMALLINT` / `INTEGER` / `BIGINT` | whole numbers, increasing size limits | `reps`, `exercise_id`, `user_id` |
| `NUMERIC(6,2)` | exact decimals — 6 digits total, 2 after the point | `weight_kg` |
| `BOOLEAN` | true / false | `is_warmup` |
| `DATE` | a calendar day, no time | `performed_on` |
| `TIMESTAMPTZ` | an exact instant, timezone-aware | `created_at` |
| `JSONB` | arbitrary JSON, queryable | `ai_programs.program` |

**Why `NUMERIC` and never `FLOAT`:** floats are binary approximations. `82.5` can't be represented exactly, and the tiny error compounds every time you `SUM()`. `NUMERIC` stores decimal digits exactly. Slower, correct. Always correct over fast for measurements and money.

**`NULL`** — "no value here," distinct from `0` or `""`. `NULL` never equals anything, including another `NULL` — which is why `exercises` needed two *partial* unique indexes instead of one constraint.

---

## Rules the database enforces

The theme: put rules in the database, not just the app. Your API will have bugs; the database is the layer that doesn't care.

**Primary key** — the column uniquely identifying each row. Every table has `id`.

**Foreign key** — a column pointing at another table's primary key. `workouts.user_id` references `users.id`. Postgres refuses to store a `user_id` that doesn't exist, which makes orphaned rows impossible.

**`ON DELETE` behaviour** — what happens to referencing rows when the referenced row is deleted:

- `CASCADE` — delete them too. Delete a user → their workouts vanish. Correct for owned data.
- `RESTRICT` — refuse the delete. Can't delete an exercise that logged sets reference. Correct for shared reference data.
- `SET NULL` — keep the row, blank the reference.

**`CHECK` constraint** — an arbitrary rule per row. `CHECK (weight_kg > 20 AND weight_kg < 400)` is what rejected the 820kg bodyweight.

**`NOT NULL`** — this column must have a value.

**`UNIQUE`** — no two rows may share this value.

**Enum** — a type restricted to a fixed list. `body_region` allows only `upper`, `lower`, `core`, `full_body`. Adding a value requires a migration; that friction is the feature.

---

## Making it fast

**Index** — a separate sorted structure letting Postgres find rows without reading the whole table. Without one, finding your workouts in 10 million rows means reading all 10 million. With one, about 4–5 page reads regardless of table size.

Cost: indexes make writes slightly slower and use disk. Worth it when you read far more than you write.

**Composite index** — spans several columns. `(user_id, performed_on DESC)` serves "this user's recent workouts" in one lookup.

**Unique index** — an index that also enforces uniqueness.

**Functional index** — built on an expression rather than a raw column. `lower(email)` is what makes `Dilpreet@X.com` and `dilpreet@x.com` collide.

**Partial index** — only covers rows matching a condition. `WHERE created_by_user_id IS NULL` makes global exercise names unique globally, while custom ones are unique per user.

**`EXPLAIN ANALYZE`** — shows the plan Postgres chose and what it actually cost. How you find out whether your index is being used.

**Cold cache** — Postgres keeps hot pages in memory; after a restart that's empty, so the first queries are slower until it refills. Why production databases aren't restarted casually.

---

## Convenience features

**View** — a saved query that behaves like a table. `v_set_details` pre-joins sets → workout_exercises → workouts → exercises, so you write that chain once instead of fifty times. Stores no data; runs underneath every time.

**Generated column** — computed by Postgres on write. `volume_kg` is `weight_kg * reps`, stored. Can't be inserted into. Computed once instead of on every read.

**Trigger** — code that fires automatically on insert/update/delete. `set_updated_at()` refreshes `updated_at` on every update, so it's correct whether the write came from your API, a migration, or psql by hand.

**Sequence / identity** — the counter behind `GENERATED ALWAYS AS IDENTITY`. Only counts up, never reuses numbers, and doesn't roll back — which is why IDs have gaps and mean nothing beyond "this row."

---

## Writing queries

**`SELECT`** — which columns to return.
**`FROM`** — which table.
**`WHERE`** — which rows.
**`GROUP BY`** — collapse rows sharing a value into one row. Four sets on one date become one row for that date.
**`ORDER BY`** — sort.
**`LIMIT`** — stop after N rows.

**Aggregate function** — squashes many values into one: `SUM()`, `AVG()`, `COUNT()`, `MAX()`, `MIN()`.

**The `GROUP BY` rule** — every column in `SELECT` must either appear in the `GROUP BY` or be inside an aggregate. Once rows are collapsed, "what's `weight_kg`?" has no single answer. Almost every `GROUP BY` error is a violation of this.

**`JOIN`** — attach rows from another table where a key matches. Watch the row count: joining `sets` to `exercise_muscle_groups` turns one bench press set into three rows (chest, front delts, triceps). Intended — and why summing across muscle groups would triple-count.

**Alias** — a nickname. `FROM v_set_details s` lets you write `s.performed_on`. Required when the same column name exists in two joined tables.

**`date_trunc('week', d)`** — snaps a date back to its Monday. How you bucket sessions into weeks. **Watch for partial weeks at the edges** — an incomplete final week looks like a collapse in volume.

**Placeholder / parameterized query** — `:exercise_id` in the SQL, with the real value passed separately. The query and the data travel to Postgres independently, so a value can never become executable SQL. Building queries with f-strings instead is **SQL injection**, still one of the most common ways real systems get breached.

---

## Managing change

**Transaction** — a group of statements that all succeed or all fail. `BEGIN` starts it, `COMMIT` makes it permanent, `ROLLBACK` undoes everything. Your whole schema loaded in one transaction, which is why a single error would have left you with zero tables rather than seven.

**Migration** — one numbered, ordered change to the schema. `0001` created tables, `0002` added exercises, `0003` added foods. Run in sequence, they rebuild the database from empty. **Never edit an applied migration** — write a new one.

**`alembic_version`** — a one-row table recording which migration a database has reached. Alembic reads it, compares against your files, runs what's missing. The bookkeeping travels with the database, which is why the same command works against Docker locally and RDS in production.

**Reference data** — the fixed vocabulary the app can't work without: muscle groups, exercises, food items. Ships to every environment, so it belongs in migrations.

**Seed / dev data** — fake data for local testing. `seed_dev_data.py`. Must never reach production, so it lives outside the migration chain.

**WAL (write-ahead log)** — Postgres records changes to a log *before* applying them to data files. If the power cuts mid-write, it replays the log on startup. This is what makes a database crash-safe.

---

## Design concepts

**Normalization** — storing each fact exactly once. Two copies eventually disagree. `focus_area` and `current_bodyweight` were both left out for this reason: derivable from data you already have, so a stored copy can only contradict it.

**Join table** (or *junction* / *intermediate table*) — a table whose purpose is connecting two others. `exercise_muscle_groups` connects exercises to muscles many-to-many, and carries extra data of its own (`contribution`).

**Denormalization** — deliberately storing a duplicate to make reads faster. Sometimes correct, always a tradeoff: you now own the problem of keeping copies in sync.

**Cardinality** — how many of one thing relate to another. One user → many workouts (one-to-many). One exercise ↔ many muscles, one muscle ↔ many exercises (many-to-many, needs a join table).
