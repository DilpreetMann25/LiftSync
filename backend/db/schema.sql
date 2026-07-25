-- ============================================================
-- LiftSync — Initial PostgreSQL Schema (v1)
-- Target: PostgreSQL 16
--
-- Design decisions worth defending in an interview:
--   1. All weights stored in KILOGRAMS. Unit conversion is a
--      presentation concern, never a storage concern. Mixed units
--      in a column is one of the most common data-integrity bugs.
--   2. NUMERIC, never FLOAT/REAL, for anything measured. Floats
--      cannot represent 82.5 exactly; errors accumulate in SUM().
--   3. workout_exercises exists so the same exercise can appear
--      twice in one session as distinct blocks, and so supersets
--      can be grouped.
--   4. There is no workouts.focus_area column. Focus area is
--      DERIVED from the muscle groups of exercises performed.
--      Derived data cannot contradict the underlying facts.
-- ============================================================

BEGIN;

-- ------------------------------------------------------------
-- Enumerated types
-- Enums constrain the vocabulary at the database level. Adding a
-- value later requires a migration -- that friction is the point.
-- ------------------------------------------------------------
CREATE TYPE unit_preference  AS ENUM ('metric', 'imperial');
CREATE TYPE exercise_category AS ENUM ('compound', 'isolation', 'cardio', 'other');
CREATE TYPE body_region       AS ENUM ('upper', 'lower', 'core', 'full_body');


-- ------------------------------------------------------------
-- users
-- ------------------------------------------------------------
CREATE TABLE users (
    id               BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    email            TEXT        NOT NULL,
    password_hash    TEXT        NOT NULL,
    display_name     TEXT        NOT NULL,
    date_of_birth    DATE,
    height_cm        NUMERIC(5,1) CHECK (height_cm > 0 AND height_cm < 300),
    units            unit_preference NOT NULL DEFAULT 'metric',
    created_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at       TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Case-insensitive uniqueness. Dilpreet@x.com and dilpreet@x.com are the
-- same person; the database should enforce that, not the application.
-- A plain UNIQUE(email) would let both rows exist.
CREATE UNIQUE INDEX users_email_ci_idx ON users (lower(email));

-- NOTE: current body weight is deliberately NOT a column here.
-- It lives in bodyweight_logs. Storing "current" separately means
-- it can drift out of sync with the log. Read the latest row instead.


-- ------------------------------------------------------------
-- muscle_groups  (reference vocabulary)
-- ------------------------------------------------------------
CREATE TABLE muscle_groups (
    id       SMALLINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    name     TEXT        NOT NULL UNIQUE,   -- 'chest', 'front_delts', 'lats'
    region   body_region NOT NULL
);


-- ------------------------------------------------------------
-- exercises  (dictionary of movements)
--
-- created_by_user_id NULL  => global exercise, visible to everyone
-- created_by_user_id SET   => a user's custom movement
-- ------------------------------------------------------------
CREATE TABLE exercises (
    id                 INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    name               TEXT              NOT NULL,
    category           exercise_category NOT NULL DEFAULT 'compound',
    equipment          TEXT,                       -- 'barbell', 'dumbbell', 'machine'
    is_unilateral      BOOLEAN           NOT NULL DEFAULT false,
    created_by_user_id BIGINT REFERENCES users(id) ON DELETE CASCADE,
    created_at         TIMESTAMPTZ       NOT NULL DEFAULT now()
);

-- Two partial unique indexes: global names are unique globally,
-- custom names are unique per user. A single UNIQUE constraint
-- cannot express this, because NULL never equals NULL.
CREATE UNIQUE INDEX exercises_global_name_idx
    ON exercises (lower(name))
    WHERE created_by_user_id IS NULL;

CREATE UNIQUE INDEX exercises_custom_name_idx
    ON exercises (created_by_user_id, lower(name))
    WHERE created_by_user_id IS NOT NULL;


-- ------------------------------------------------------------
-- exercise_muscle_groups  (many-to-many, weighted)
--
-- THIS TABLE IS THE ONE THAT MAKES THE AI COACH POSSIBLE.
-- "Show me 8 weeks of shoulder volume" resolves through here.
--
-- contribution: how much of a set's volume counts toward this
-- muscle group. Overhead press -> front_delts 1.0, triceps 0.5.
-- Bench press   -> chest 1.0, front_delts 0.4, triceps 0.5.
-- ------------------------------------------------------------
CREATE TABLE exercise_muscle_groups (
    exercise_id     INTEGER  NOT NULL REFERENCES exercises(id)     ON DELETE CASCADE,
    muscle_group_id SMALLINT NOT NULL REFERENCES muscle_groups(id) ON DELETE RESTRICT,
    contribution    NUMERIC(3,2) NOT NULL DEFAULT 1.00
                    CHECK (contribution > 0 AND contribution <= 1),
    PRIMARY KEY (exercise_id, muscle_group_id)
);
-- ON DELETE RESTRICT above: deleting a muscle group that exercises
-- reference should FAIL loudly rather than silently shred your mappings.


-- ------------------------------------------------------------
-- workouts  (one training session)
-- ------------------------------------------------------------
CREATE TABLE workouts (
    id           BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    user_id      BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    performed_on DATE   NOT NULL,          -- the training DAY (what you filter on)
    started_at   TIMESTAMPTZ,              -- optional precise timing
    ended_at     TIMESTAMPTZ,
    notes        TEXT,                     -- free text is CORRECT here: never aggregated
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now(),

    CONSTRAINT workouts_time_order CHECK (ended_at IS NULL OR started_at IS NULL
                                          OR ended_at >= started_at)
);
-- Deliberately NO unique(user_id, performed_on): two-a-days are real.


-- ------------------------------------------------------------
-- workout_exercises
-- An exercise AS PERFORMED within a specific session.
--
-- order_index      -> position in the session (bench first, bench again later)
-- superset_group   -> rows sharing a value within one workout were
--                     performed alternating. NULL = straight sets.
-- ------------------------------------------------------------
CREATE TABLE workout_exercises (
    id             BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    workout_id     BIGINT   NOT NULL REFERENCES workouts(id)  ON DELETE CASCADE,
    exercise_id    INTEGER  NOT NULL REFERENCES exercises(id) ON DELETE RESTRICT,
    order_index    SMALLINT NOT NULL CHECK (order_index >= 0),
    superset_group SMALLINT CHECK (superset_group >= 0),
    notes          TEXT,

    CONSTRAINT workout_exercises_order_key UNIQUE (workout_id, order_index)
);


-- ------------------------------------------------------------
-- sets
-- The atomic unit of training. Links to workout_exercise, NOT
-- directly to exercise -- the exercise is reachable by join.
-- Storing exercise_id here too would be denormalization: a second
-- copy of a fact that can drift from the first.
-- ------------------------------------------------------------
CREATE TABLE sets (
    id                  BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    workout_exercise_id BIGINT   NOT NULL REFERENCES workout_exercises(id) ON DELETE CASCADE,
    set_number          SMALLINT NOT NULL CHECK (set_number > 0),
    weight_kg           NUMERIC(6,2) NOT NULL CHECK (weight_kg >= 0),
    reps                SMALLINT     NOT NULL CHECK (reps > 0),
    rpe                 NUMERIC(3,1) CHECK (rpe >= 1 AND rpe <= 10),
    is_warmup           BOOLEAN  NOT NULL DEFAULT false,

    -- Generated column: Postgres computes and stores this on write.
    -- Volume is used in almost every analytics query; computing it
    -- once at write time beats recomputing it on every read.
    volume_kg           NUMERIC(10,2)
                        GENERATED ALWAYS AS (weight_kg * reps) STORED,

    CONSTRAINT sets_number_key UNIQUE (workout_exercise_id, set_number)
);


-- ------------------------------------------------------------
-- bodyweight_logs
-- ------------------------------------------------------------
CREATE TABLE bodyweight_logs (
    id          BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    user_id     BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    measured_on DATE   NOT NULL,
    weight_kg   NUMERIC(5,2) NOT NULL CHECK (weight_kg > 20 AND weight_kg < 400),
    notes       TEXT,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),

    -- One weigh-in per user per day. Re-weighing updates the row.
    CONSTRAINT bodyweight_logs_daily_key UNIQUE (user_id, measured_on)
);


-- ------------------------------------------------------------
-- nutrition_logs  (daily rollup)
-- ------------------------------------------------------------
CREATE TABLE nutrition_logs (
    id         BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    user_id    BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    logged_on  DATE   NOT NULL,
    calories   INTEGER      CHECK (calories   >= 0),
    protein_g  NUMERIC(6,2) CHECK (protein_g  >= 0),
    carbs_g    NUMERIC(6,2) CHECK (carbs_g    >= 0),
    fat_g      NUMERIC(6,2) CHECK (fat_g      >= 0),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),

    CONSTRAINT nutrition_logs_daily_key UNIQUE (user_id, logged_on)
);


-- ------------------------------------------------------------
-- food_items  (dictionary -- whey, chicken breast, whole eggs)
-- Macros per 100g so any quantity scales cleanly.
-- ------------------------------------------------------------
CREATE TABLE food_items (
    id                 INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    name               TEXT NOT NULL,
    protein_per_100g   NUMERIC(5,2) NOT NULL CHECK (protein_per_100g >= 0),
    carbs_per_100g     NUMERIC(5,2) NOT NULL DEFAULT 0 CHECK (carbs_per_100g >= 0),
    fat_per_100g       NUMERIC(5,2) NOT NULL DEFAULT 0 CHECK (fat_per_100g   >= 0),
    calories_per_100g  NUMERIC(6,2) NOT NULL CHECK (calories_per_100g >= 0),
    is_protein_source  BOOLEAN NOT NULL DEFAULT false,
    created_by_user_id BIGINT REFERENCES users(id) ON DELETE CASCADE
);

CREATE UNIQUE INDEX food_items_global_name_idx
    ON food_items (lower(name)) WHERE created_by_user_id IS NULL;


-- ------------------------------------------------------------
-- nutrition_entries  (individual foods within a day)
-- This is what satisfies "track specific protein sources".
-- ------------------------------------------------------------
CREATE TABLE nutrition_entries (
    id               BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    nutrition_log_id BIGINT  NOT NULL REFERENCES nutrition_logs(id) ON DELETE CASCADE,
    food_item_id     INTEGER NOT NULL REFERENCES food_items(id)     ON DELETE RESTRICT,
    quantity_g       NUMERIC(7,2) NOT NULL CHECK (quantity_g > 0),
    consumed_at      TIMESTAMPTZ
);


-- ------------------------------------------------------------
-- ai_programs
-- Every AI-generated block is persisted with the exact context it
-- was built from. Without this you can never answer "why did the
-- coach say that?" -- and you cannot evaluate whether it worked.
-- ------------------------------------------------------------
CREATE TABLE ai_programs (
    id                 BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    user_id            BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    target_exercise_id INTEGER REFERENCES exercises(id) ON DELETE SET NULL,
    user_prompt        TEXT   NOT NULL,
    model              TEXT   NOT NULL,          -- 'claude-sonnet-5'
    tool_calls         JSONB,                    -- audit trail of what the agent queried
    context_snapshot   JSONB,                    -- the data it actually saw
    program            JSONB  NOT NULL,          -- the structured 4-week block
    input_tokens       INTEGER,
    output_tokens      INTEGER,
    created_at         TIMESTAMPTZ NOT NULL DEFAULT now()
);


-- ============================================================
-- INDEXES
--
-- Rule of thumb: index every foreign key you join on, and every
-- (user_id, date) pair you filter ranges on. An index makes reads
-- fast and writes slightly slower -- this app reads far more than
-- it writes, so the trade is easy.
-- ============================================================
CREATE INDEX workouts_user_date_idx           ON workouts (user_id, performed_on DESC);
CREATE INDEX workout_exercises_workout_idx    ON workout_exercises (workout_id);
CREATE INDEX workout_exercises_exercise_idx   ON workout_exercises (exercise_id);
CREATE INDEX sets_workout_exercise_idx        ON sets (workout_exercise_id);
CREATE INDEX bodyweight_user_date_idx         ON bodyweight_logs (user_id, measured_on DESC);
CREATE INDEX nutrition_user_date_idx          ON nutrition_logs (user_id, logged_on DESC);
CREATE INDEX nutrition_entries_log_idx        ON nutrition_entries (nutrition_log_id);
CREATE INDEX emg_muscle_group_idx             ON exercise_muscle_groups (muscle_group_id);
CREATE INDEX ai_programs_user_idx             ON ai_programs (user_id, created_at DESC);


-- ============================================================
-- updated_at maintenance
-- Doing this in a trigger means it is correct no matter what
-- writes to the table -- your API, a migration, or psql by hand.
-- ============================================================
CREATE OR REPLACE FUNCTION set_updated_at() RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = now();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER users_set_updated_at
    BEFORE UPDATE ON users
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();

CREATE TRIGGER nutrition_logs_set_updated_at
    BEFORE UPDATE ON nutrition_logs
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();


-- ============================================================
-- v_set_details
-- A view flattening the join chain you will otherwise write
-- fifty times. Analytics queries read from this.
-- ============================================================
CREATE VIEW v_set_details AS
SELECT
    s.id              AS set_id,
    w.user_id,
    w.id              AS workout_id,
    w.performed_on,
    we.id             AS workout_exercise_id,
    we.order_index,
    we.superset_group,
    e.id              AS exercise_id,
    e.name            AS exercise_name,
    e.category,
    s.set_number,
    s.weight_kg,
    s.reps,
    s.rpe,
    s.is_warmup,
    s.volume_kg
FROM sets s
JOIN workout_exercises we ON we.id = s.workout_exercise_id
JOIN workouts          w  ON w.id  = we.workout_id
JOIN exercises         e  ON e.id  = we.exercise_id;

COMMIT;
