-- ============================================================
-- Migration 0003 — Food items reference data
--
-- Macros are per 100g so any quantity scales by simple arithmetic.
-- Values are raw/dry weight where that is how the food is normally
-- weighed (chicken, oats, rice is cooked).
--
-- is_protein_source flags the foods the AI Coach should surface when
-- reasoning about protein intake. Rice is not a protein source even
-- though it contains protein.
-- ============================================================

INSERT INTO food_items
    (name, protein_per_100g, carbs_per_100g, fat_per_100g, calories_per_100g, is_protein_source)
VALUES
    ('Whey Protein Isolate',  85.00,  5.00,   1.00, 375.00, true),
    ('Chicken Breast (raw)',  23.00,  0.00,   2.60, 120.00, true),
    ('Whole Eggs',            12.60,  1.10,   9.50, 143.00, true),
    ('Egg Whites',            11.00,  0.70,   0.20,  52.00, true),
    ('Greek Yogurt (0%)',     10.00,  3.60,   0.40,  59.00, true),
    ('Salmon Fillet',         20.00,  0.00,  13.00, 208.00, true),
    ('Paneer',                18.00,  1.20,  20.00, 265.00, true),
    ('Lentils (cooked)',       9.00, 20.00,   0.40, 116.00, true),
    ('Milk (2%)',              3.40,  4.80,   2.00,  50.00, true),
    ('White Rice (cooked)',    2.70, 28.00,   0.30, 130.00, false),
    ('Oats (dry)',            13.00, 67.00,   7.00, 389.00, false),
    ('Banana',                 1.10, 23.00,   0.30,  89.00, false),
    ('Almonds',               21.00, 22.00,  50.00, 579.00, false),
    ('Peanut Butter',         25.00, 20.00,  50.00, 588.00, false),
    ('Olive Oil',              0.00,  0.00, 100.00, 884.00, false)
ON CONFLICT (lower(name)) WHERE created_by_user_id IS NULL DO NOTHING;
