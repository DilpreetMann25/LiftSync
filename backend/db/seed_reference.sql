-- ============================================================
-- LiftSync — Reference / Seed Data
--
-- "Reference data" = the fixed vocabulary the app needs to work at
-- all. It is NOT user data. Muscle groups and standard exercises
-- exist before anybody signs up.
--
-- Run AFTER schema.sql:
--   docker compose exec -T db psql -U liftsync -d liftsync < backend/db/seed_reference.sql
--
-- Safe to re-run: every insert ends with ON CONFLICT DO NOTHING.
-- ============================================================

BEGIN;

-- ------------------------------------------------------------
-- 1. muscle_groups
--
-- Deliberately granular. "Shoulders" is useless to the AI Coach --
-- an overhead press and a rear-delt fly are both "shoulders" but
-- train almost nothing in common. Splitting the delts into three
-- is what lets the agent say something specific.
-- ------------------------------------------------------------
INSERT INTO muscle_groups (name, region) VALUES
    ('chest',       'upper'),
    ('front_delts', 'upper'),
    ('side_delts',  'upper'),
    ('rear_delts',  'upper'),
    ('lats',        'upper'),
    ('mid_back',    'upper'),   -- traps + rhomboids
    ('biceps',      'upper'),
    ('triceps',     'upper'),
    ('forearms',    'upper'),
    ('quads',       'lower'),
    ('hamstrings',  'lower'),
    ('glutes',      'lower'),
    ('calves',      'lower'),
    ('abs',         'core'),
    ('lower_back',  'core')
ON CONFLICT (name) DO NOTHING;


-- ------------------------------------------------------------
-- 2. exercises
--
-- created_by_user_id is left NULL => these are GLOBAL exercises,
-- available to every user. A user's custom movement would set it.
--
-- ON CONFLICT needs the constraint spelled out as a WHERE clause
-- because the uniqueness is enforced by a PARTIAL index
-- (exercises_global_name_idx), not a plain UNIQUE constraint.
-- ------------------------------------------------------------
INSERT INTO exercises (name, category, equipment) VALUES
    -- ---- worked examples (mappings provided below) ----
    ('Barbell Bench Press',  'compound',  'barbell'),
    ('Barbell Back Squat',   'compound',  'barbell'),
    ('Overhead Press',       'compound',  'barbell'),

    -- ---- YOUR TURN: these have NO muscle mappings yet ----
    ('Conventional Deadlift','compound',  'barbell'),
    ('Barbell Row',          'compound',  'barbell'),
    ('Pull-Up',              'compound',  'bodyweight'),
    ('Incline Dumbbell Press','compound', 'dumbbell'),
    ('Romanian Deadlift',    'compound',  'barbell'),
    ('Leg Press',            'compound',  'machine'),
    ('Dumbbell Lateral Raise','isolation','dumbbell'),
    ('Face Pull',            'isolation', 'cable'),
    ('Barbell Curl',         'isolation', 'barbell'),
    ('Cable Tricep Pushdown','isolation', 'cable'),
    ('Lying Leg Curl',       'isolation', 'machine'),
    ('Standing Calf Raise',  'isolation', 'machine')
ON CONFLICT (lower(name)) WHERE created_by_user_id IS NULL DO NOTHING;


-- ------------------------------------------------------------
-- 3. exercise_muscle_groups   <-- THE IMPORTANT ONE
--
-- contribution (0.01 - 1.00): what fraction of a set's volume
-- counts toward this muscle group.
--
--   1.00 = this is the primary target, taking the full stimulus
--   0.50 = meaningful secondary involvement
--   0.20 = minor, but real
--
-- These numbers ARE the AI Coach's understanding of anatomy. When
-- it reports "your shoulder volume dropped 30%", that number came
-- from this table. Wrong values here = confidently wrong coaching.
--
-- The pattern below looks up IDs BY NAME rather than hardcoding
-- 1, 2, 3. IDs are GENERATED ALWAYS AS IDENTITY -- you don't
-- control them, and they change if you reseed. Never hardcode them.
-- ------------------------------------------------------------
INSERT INTO exercise_muscle_groups (exercise_id, muscle_group_id, contribution)
SELECT e.id, m.id, v.contribution
FROM (VALUES
    -- exercise                muscle          contribution
    ('Barbell Bench Press',   'chest',         1.00),
    ('Barbell Bench Press',   'front_delts',   0.40),
    ('Barbell Bench Press',   'triceps',       0.50),

    ('Barbell Back Squat',    'quads',         1.00),
    ('Barbell Back Squat',    'glutes',        0.80),
    ('Barbell Back Squat',    'hamstrings',    0.40),
    ('Barbell Back Squat',    'lower_back',    0.30),
    ('Barbell Back Squat',    'abs',           0.30),

    ('Overhead Press',        'front_delts',   1.00),
    ('Overhead Press',        'side_delts',    0.50),
    ('Overhead Press',        'triceps',       0.60),
    ('Overhead Press',        'chest',         0.20),
    ('Overhead Press',        'abs',           0.30),

    ('Conventional Deadlift', 'hamstrings',    1.00),
    ('Conventional Deadlift','glutes',        0.80),
    ('Conventional Deadlift', 'lower_back',    0.70),
    ('Conventional Deadlift', 'mid_back',      0.50),   -- isometric: holds the bar path tight
    ('Conventional Deadlift', 'quads',         0.30),
    ('Conventional Deadlift', 'forearms',      0.20),

    ('Barbell Row',           'lats',          1.00),
    ('Barbell Row',           'mid_back',      0.80),
    ('Barbell Row',           'rear_delts',    0.50),
    ('Barbell Row',           'biceps',        0.30),
    ('Barbell Row',           'forearms',      0.20),

    ('Pull-Up',               'lats',          1.00),
    ('Pull-Up',               'biceps',        0.50),
    ('Pull-Up',               'mid_back',      0.40),
    ('Pull-Up',               'rear_delts',    0.30),
    ('Pull-Up',               'forearms',      0.20),

    ('Incline Dumbbell Press', 'chest',         1.00),
    ('Incline Dumbbell Press','front_delts',   0.50),
    ('Incline Dumbbell Press','triceps',       0.30),

    ('Romanian Deadlift',    'hamstrings',    1.00),
    ('Romanian Deadlift',      'glutes',        0.80),
    ('Romanian Deadlift',      'lower_back',    0.50),
    ('Romanian Deadlift',      'forearms',      0.20),

    ('Leg Press',            'quads',         1.00),
    ('Leg Press',              'glutes',        0.80),
    ('Leg Press',              'hamstrings',    0.40),

    ('Dumbbell Lateral Raise', 'side_delts',    1.00),

    ('Face Pull',            'rear_delts',    1.00),
    ('Face Pull',              'side_delts',    0.50),
    ('Face Pull',              'mid_back',      0.30),

    ('Barbell Curl',           'biceps',        1.00),
    ('Barbell Curl',           'forearms',      0.30),

    ('Cable Tricep Pushdown', 'triceps',       1.00),
    ('Cable Tricep Pushdown', 'forearms',      0.20),

    ('Lying Leg Curl',        'hamstrings',    1.00),
    ('Lying Leg Curl',          'glutes',        0.30),

    ('Standing Calf Raise',     'calves',        1.00)

) AS v(exercise_name, muscle_name, contribution)
JOIN exercises     e ON e.name = v.exercise_name AND e.created_by_user_id IS NULL
JOIN muscle_groups m ON m.name = v.muscle_name
ON CONFLICT (exercise_id, muscle_group_id) DO NOTHING;

COMMIT;


-- ============================================================
-- VERIFY YOUR WORK
-- Run this after adding your rows. Any exercise showing 0 muscle
-- groups is invisible to the AI Coach -- its volume will silently
-- vanish from every muscle-group query.
-- ============================================================
--
--  SELECT e.name,
--         COUNT(emg.muscle_group_id) AS muscles_mapped,
--         COALESCE(SUM(emg.contribution), 0) AS total_contribution
--  FROM exercises e
--  LEFT JOIN exercise_muscle_groups emg ON emg.exercise_id = e.id
--  GROUP BY e.name
--  ORDER BY muscles_mapped ASC, e.name;
--
-- ============================================================
-- AND A SANITY CHECK ON YOUR JUDGEMENT
-- This is the query shape your AI Coach will actually use.
-- It should list front_delts near the top:
--
--  SELECT m.name, ROUND(SUM(emg.contribution), 2) AS total_across_exercises
--  FROM muscle_groups m
--  JOIN exercise_muscle_groups emg ON emg.muscle_group_id = m.id
--  GROUP BY m.name
--  ORDER BY total_across_exercises DESC;
-- ============================================================
