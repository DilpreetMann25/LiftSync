-- ============================================================
-- Migration 0002 — Reference data
--
-- FROZEN once applied. New exercises go in a new migration.
--
-- "Reference data" is the fixed vocabulary the app needs to work at
-- all: muscle groups and standard movements exist before anybody
-- signs up. It belongs in a migration for the same reason the tables
-- do -- every environment must end up with identical values.
--
-- Every insert is idempotent (ON CONFLICT DO NOTHING), so re-running
-- is harmless.
-- ============================================================

-- 1. muscle_groups ---------------------------------------------
-- Deliberately granular. "Shoulders" is useless to the AI Coach: an
-- overhead press and a rear-delt fly are both "shoulders" but train
-- almost nothing in common.
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


-- 2. exercises -------------------------------------------------
-- created_by_user_id left NULL => global, available to every user.
--
-- The ON CONFLICT target repeats the index PREDICATE because
-- uniqueness here comes from a PARTIAL index, not a plain
-- constraint. Postgres needs to know which index you mean.
INSERT INTO exercises (name, category, equipment) VALUES
    ('Barbell Bench Press',    'compound',  'barbell'),
    ('Barbell Back Squat',     'compound',  'barbell'),
    ('Overhead Press',         'compound',  'barbell'),
    ('Conventional Deadlift',  'compound',  'barbell'),
    ('Barbell Row',            'compound',  'barbell'),
    ('Pull-Up',                'compound',  'bodyweight'),
    ('Incline Dumbbell Press', 'compound',  'dumbbell'),
    ('Romanian Deadlift',      'compound',  'barbell'),
    ('Leg Press',              'compound',  'machine'),
    ('Dumbbell Lateral Raise', 'isolation', 'dumbbell'),
    ('Face Pull',              'isolation', 'cable'),
    ('Barbell Curl',           'isolation', 'barbell'),
    ('Cable Tricep Pushdown',  'isolation', 'cable'),
    ('Lying Leg Curl',         'isolation', 'machine'),
    ('Standing Calf Raise',    'isolation', 'machine')
ON CONFLICT (lower(name)) WHERE created_by_user_id IS NULL DO NOTHING;


-- 3. exercise_muscle_groups ------------------------------------
-- contribution (0.01-1.00): fraction of a set's volume counting
-- toward this muscle group.
--   1.00 = primary target, full stimulus
--   0.50 = meaningful secondary involvement
--   0.20 = minor, but real
--
-- These numbers ARE the AI Coach's model of anatomy. When it reports
-- "your shoulder volume dropped 30%", the number came from here.
--
-- IDs are looked up BY NAME rather than hardcoded, because they are
-- GENERATED ALWAYS AS IDENTITY -- you do not control their values.
INSERT INTO exercise_muscle_groups (exercise_id, muscle_group_id, contribution)
SELECT e.id, m.id, v.contribution
FROM (VALUES
    -- exercise                 muscle          contribution
    ('Barbell Bench Press',     'chest',         1.00),
    ('Barbell Bench Press',     'front_delts',   0.40),
    ('Barbell Bench Press',     'triceps',       0.50),

    ('Barbell Back Squat',      'quads',         1.00),
    ('Barbell Back Squat',      'glutes',        0.80),
    ('Barbell Back Squat',      'hamstrings',    0.40),
    ('Barbell Back Squat',      'lower_back',    0.30),
    ('Barbell Back Squat',      'abs',           0.30),

    ('Overhead Press',          'front_delts',   1.00),
    ('Overhead Press',          'side_delts',    0.50),
    ('Overhead Press',          'triceps',       0.60),
    ('Overhead Press',          'chest',         0.20),
    ('Overhead Press',          'abs',           0.30),

    ('Conventional Deadlift',   'hamstrings',    1.00),
    ('Conventional Deadlift',   'glutes',        0.80),
    ('Conventional Deadlift',   'lower_back',    0.70),
    ('Conventional Deadlift',   'mid_back',      0.50),  -- isometric: holds bar path tight
    ('Conventional Deadlift',   'quads',         0.30),
    ('Conventional Deadlift',   'forearms',      0.20),

    ('Barbell Row',             'lats',          1.00),
    ('Barbell Row',             'mid_back',      0.80),
    ('Barbell Row',             'rear_delts',    0.50),
    ('Barbell Row',             'biceps',        0.30),
    ('Barbell Row',             'forearms',      0.20),

    ('Pull-Up',                 'lats',          1.00),
    ('Pull-Up',                 'biceps',        0.50),
    ('Pull-Up',                 'mid_back',      0.40),
    ('Pull-Up',                 'rear_delts',    0.30),
    ('Pull-Up',                 'forearms',      0.20),

    ('Incline Dumbbell Press',  'chest',         1.00),
    ('Incline Dumbbell Press',  'front_delts',   0.50),
    ('Incline Dumbbell Press',  'triceps',       0.30),

    ('Romanian Deadlift',       'hamstrings',    1.00),
    ('Romanian Deadlift',       'glutes',        0.80),
    ('Romanian Deadlift',       'lower_back',    0.50),
    ('Romanian Deadlift',       'forearms',      0.20),

    ('Leg Press',               'quads',         1.00),
    ('Leg Press',               'glutes',        0.80),
    ('Leg Press',               'hamstrings',    0.40),

    ('Dumbbell Lateral Raise',  'side_delts',    1.00),

    ('Face Pull',               'rear_delts',    1.00),
    ('Face Pull',               'side_delts',    0.50),
    ('Face Pull',               'mid_back',      0.30),

    ('Barbell Curl',            'biceps',        1.00),
    ('Barbell Curl',            'forearms',      0.30),

    ('Cable Tricep Pushdown',   'triceps',       1.00),
    ('Cable Tricep Pushdown',   'forearms',      0.20),

    ('Lying Leg Curl',          'hamstrings',    1.00),
    ('Lying Leg Curl',          'glutes',        0.30),

    ('Standing Calf Raise',     'calves',        1.00)
) AS v(exercise_name, muscle_name, contribution)
JOIN exercises     e ON e.name = v.exercise_name AND e.created_by_user_id IS NULL
JOIN muscle_groups m ON m.name = v.muscle_name
ON CONFLICT (exercise_id, muscle_group_id) DO NOTHING;
