-- ============================================================
-- Migration 0001 — Initial schema
--
-- FROZEN. Once this has run anywhere, never edit it. Changes go in
-- a NEW migration. Editing an applied migration means your database
-- and your migration history disagree, and Alembic has no way to
-- detect that.
--
-- No BEGIN/COMMIT here: Alembic already wraps every migration in a
-- transaction. Nesting one inside would break its rollback handling.
-- ============================================================

CREATE TYPE unit_preference   AS ENUM ('metric', 'imperial');
CREATE TYPE exercise_category AS ENUM ('compound', 'isolation', 'cardio', 'other');
CREATE TYPE body_region       AS ENUM ('upper', 'lower', 'core', 'full_body');


-- users --------------------------------------------------------
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

-- Case-insensitive uniqueness, enforced by the database rather than
-- the application. A plain UNIQUE(email) would allow both
-- dilpreet@x.com and Dilpreet@X.com.
CREATE UNIQUE INDEX users_email_ci_idx ON users (lower(email));

-- NOTE: no current_bodyweight column. It lives in bodyweight_logs;
-- a stored copy would drift out of sync with the log.


-- muscle_groups ------------------------------------------------
CREATE TABLE muscle_groups (
    id       SMALLINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    name     TEXT        NOT NULL UNIQUE,
    region   body_region NOT NULL
);


-- exercises ----------------------------------------------------
-- created_by_user_id NULL => global movement, visible to everyone
-- created_by_user_id SET  => a user's custom movement
CREATE TABLE exercises (
    id                 INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    name               TEXT              NOT NULL,
    category           exercise_category NOT NULL DEFAULT 'compound',
    equipment          TEXT,
    is_unilateral      BOOLEAN           NOT NULL DEFAULT false,
    created_by_user_id BIGINT REFERENCES users(id) ON DELETE CASCADE,
    created_at         TIMESTAMPTZ       NOT NULL DEFAULT now()
);

-- Two PARTIAL unique indexes: global names unique globally, custom
-- names unique per user. One UNIQUE constraint cannot express this,
-- because NULL never equals NULL.
CREATE UNIQUE INDEX exercises_global_name_idx
    ON exercises (lower(name))
    WHERE created_by_user_id IS NULL;

CREATE UNIQUE INDEX exercises_custom_name_idx
    ON exercises (created_by_user_id, lower(name))
    WHERE created_by_user_id IS NOT NULL;


-- exercise_muscle_groups ---------------------------------------
-- The table that makes the AI Coach possible. "8 weeks of shoulder
-- volume" resolves through here.
--
-- contribution: fraction of a set's volume counting toward this
-- muscle. Overhead press -> front_delts 1.0, triceps 0.6.
CREATE TABLE exercise_muscle_groups (
    exercise_id     INTEGER  NOT NULL REFERENCES exercises(id)     ON DELETE CASCADE,
    muscle_group_id SMALLINT NOT NULL REFERENCES muscle_groups(id) ON DELETE RESTRICT,
    contribution    NUMERIC(3,2) NOT NULL DEFAULT 1.00
                    CHECK (contribution > 0 AND contribution <= 1),
    PRIMARY KEY (exercise_id, muscle_group_id)
);


-- workouts -----------------------------------------------------
CREATE TABLE workouts (
    id           BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    user_id      BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    performed_on DATE   NOT NULL,
    started_at   TIMESTAMPTZ,
    ended_at     TIMESTAMPTZ,
    notes        TEXT,     -- free text is CORRECT here: never aggregated
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now(),

    CONSTRAINT workouts_time_order CHECK (ended_at IS NULL OR started_at IS NULL
                                          OR ended_at >= started_at)
);
-- Deliberately NO unique(user_id, performed_on): two-a-days are real.

-- NOTE: no focus_area column. Focus area is DERIVED from the muscle
-- groups of the exercises actually performed. Derived data cannot
-- contradict the underlying facts.


-- workout_exercises --------------------------------------------
-- An exercise AS PERFORMED within one session.
--   order_index    -> position in the session
--   superset_group -> rows sharing a value were performed alternating
CREATE TABLE workout_exercises (
    id             BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    workout_id     BIGINT   NOT NULL REFERENCES workouts(id)  ON DELETE CASCADE,
    exercise_id    INTEGER  NOT NULL REFERENCES exercises(id) ON DELETE RESTRICT,
    order_index    SMALLINT NOT NULL CHECK (order_index >= 0),
    superset_group SMALLINT CHECK (superset_group >= 0),
    notes          TEXT,

    CONSTRAINT workout_exercises_order_key UNIQUE (workout_id, order_index)
);


-- sets ---------------------------------------------------------
CREATE TABLE sets (
    id                  BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    workout_exercise_id BIGINT   NOT NULL REFERENCES workout_exercises(id) ON DELETE CASCADE,
    set_number          SMALLINT NOT NULL CHECK (set_number > 0),
    weight_kg           NUMERIC(6,2) NOT NULL CHECK (weight_kg >= 0),
    reps                SMALLINT     NOT NULL CHECK (reps > 0),
    rpe                 NUMERIC(3,1) CHECK (rpe >= 1 AND rpe <= 10),
    is_warmup           BOOLEAN  NOT NULL DEFAULT false,

    -- Computed by Postgres on write, not on every read.
    volume_kg           NUMERIC(10,2)
                        GENERATED ALWAYS AS (weight_kg * reps) STORED,

    CONSTRAINT sets_number_key UNIQUE (workout_exercise_id, set_number)
);


-- bodyweight_logs ----------------------------------------------
CREATE TABLE bodyweight_logs (
    id          BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    user_id     BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    measured_on DATE   NOT NULL,
    weight_kg   NUMERIC(5,2) NOT NULL CHECK (weight_kg > 20 AND weight_kg < 400),
    notes       TEXT,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),

    CONSTRAINT bodyweight_logs_daily_key UNIQUE (user_id, measured_on)
);


-- nutrition_logs -----------------------------------------------
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


-- food_items ---------------------------------------------------
-- Macros per 100g so any quantity scales cleanly.
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


-- nutrition_entries --------------------------------------------
-- Individual foods within a day. This is what satisfies
-- "track specific protein sources".
CREATE TABLE nutrition_entries (
    id               BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    nutrition_log_id BIGINT  NOT NULL REFERENCES nutrition_logs(id) ON DELETE CASCADE,
    food_item_id     INTEGER NOT NULL REFERENCES food_items(id)     ON DELETE RESTRICT,
    quantity_g       NUMERIC(7,2) NOT NULL CHECK (quantity_g > 0),
    consumed_at      TIMESTAMPTZ
);


-- ai_programs --------------------------------------------------
-- Every generated block persisted with the exact context it was
-- built from -- otherwise you can never answer "why did the coach
-- say that?", nor evaluate whether it worked.
CREATE TABLE ai_programs (
    id                 BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    user_id            BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    target_exercise_id INTEGER REFERENCES exercises(id) ON DELETE SET NULL,
    user_prompt        TEXT   NOT NULL,
    model              TEXT   NOT NULL,
    tool_calls         JSONB,
    context_snapshot   JSONB,
    program            JSONB  NOT NULL,
    input_tokens       INTEGER,
    output_tokens      INTEGER,
    created_at         TIMESTAMPTZ NOT NULL DEFAULT now()
);


-- indexes ------------------------------------------------------
-- Rule of thumb: index every foreign key you join on, and every
-- (user_id, date) pair you filter ranges on.
CREATE INDEX workouts_user_date_idx         ON workouts (user_id, performed_on DESC);
CREATE INDEX workout_exercises_workout_idx  ON workout_exercises (workout_id);
CREATE INDEX workout_exercises_exercise_idx ON workout_exercises (exercise_id);
CREATE INDEX sets_workout_exercise_idx      ON sets (workout_exercise_id);
CREATE INDEX bodyweight_user_date_idx       ON bodyweight_logs (user_id, measured_on DESC);
CREATE INDEX nutrition_user_date_idx        ON nutrition_logs (user_id, logged_on DESC);
CREATE INDEX nutrition_entries_log_idx      ON nutrition_entries (nutrition_log_id);
CREATE INDEX emg_muscle_group_idx           ON exercise_muscle_groups (muscle_group_id);
CREATE INDEX ai_programs_user_idx           ON ai_programs (user_id, created_at DESC);


-- updated_at trigger -------------------------------------------
-- In a trigger so it stays correct no matter what writes to the
-- table: your API, a migration, or psql by hand.
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


-- v_set_details ------------------------------------------------
-- Flattens the join chain you would otherwise write fifty times.
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
