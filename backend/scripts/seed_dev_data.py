"""Generate 8 weeks of realistic fake training data for development.

    python backend/scripts/seed_dev_data.py

THIS IS NOT A MIGRATION. Migrations describe things every environment
needs (tables, muscle groups, food items). This is throwaway demo data
that must never reach production, so it lives outside the migration
chain and only runs when you deliberately run it.

Safe to re-run: it deletes the demo user first, and ON DELETE CASCADE
removes every workout, set, and log belonging to them.

WHAT IS DELIBERATELY BAKED INTO THE NUMBERS
-------------------------------------------
Random data is useless for testing analytics -- there would be no
trend to find. So this generator encodes specific, detectable stories:

  * Bench press and squat progress steadily for all 8 weeks.
  * Overhead press progresses to 60kg by week 5, then STALLS for the
    final 3 weeks. This is the plateau your AI Coach must detect.
  * Bodyweight drifts 81kg -> 84kg with daily noise.
  * Protein intake drops hard on weekends (~185g -> ~135g).

If your Phase 3 analytics cannot find the OHP plateau, the analytics
are wrong -- because we know it is there.
"""

from __future__ import annotations

import os
import random
import sys
from datetime import date, timedelta
from pathlib import Path

import psycopg
from dotenv import load_dotenv

REPO_ROOT = Path(__file__).resolve().parents[2]
BACKEND_DIR = Path(__file__).resolve().parents[1]
load_dotenv(REPO_ROOT / ".env")

# This script lives in backend/scripts/, so Python puts THAT directory
# on the import path -- not backend/. Adding backend/ lets us reuse
# app.security instead of duplicating the hashing logic here. Two
# implementations of password hashing in one repo is how they drift
# apart and one of them ends up weaker.
sys.path.insert(0, str(BACKEND_DIR))

from app.security import hash_password  # noqa: E402  (import after sys.path fix)

# Fixed seed => identical data every run. Reproducibility matters:
# without it, a query that works today might fail tomorrow and you
# would not know whether the bug was the query or the data.
random.seed(42)

DEMO_EMAIL = "demo@liftsync.app"

# A real, properly hashed password -- so anyone who clones this repo
# can log in and see 8 weeks of data immediately, instead of having to
# register and then wonder why every endpoint returns 404.
#
# Committing a password in plaintext is normally unforgivable. It is
# fine here for the same reason `devpassword` in docker-compose.yml is
# fine: this account only ever exists in a local, disposable database
# that this script created. It is demo furniture, not a credential.
DEMO_PASSWORD = "liftsync-demo-2026"

WEEKS = 8
SESSIONS_PER_WEEK = 4


# ---------------------------------------------------------------
# Program definition
# ---------------------------------------------------------------
# weekday(): Monday=0 ... Sunday=6
# Push / Pull / Legs / Upper, four days a week.
SPLIT: dict[int, list[str]] = {
    0: ["Barbell Bench Press", "Overhead Press", "Incline Dumbbell Press",
        "Cable Tricep Pushdown"],
    1: ["Barbell Row", "Pull-Up", "Barbell Curl", "Face Pull"],
    3: ["Barbell Back Squat", "Romanian Deadlift", "Leg Press",
        "Lying Leg Curl", "Standing Calf Raise"],
    5: ["Barbell Bench Press", "Overhead Press", "Dumbbell Lateral Raise",
        "Face Pull"],
}

# start weight, increment, weeks between increments, stall_after_week
# stall_after_week=None means it never stops progressing.
PROGRESSION: dict[str, tuple[float, float, int, int | None]] = {
    "Barbell Bench Press":    (80.0,  2.5, 2, None),
    "Barbell Back Squat":     (100.0, 5.0, 2, None),
    "Overhead Press":         (55.0,  2.5, 2, 4),      # <-- the plateau
    "Barbell Row":            (70.0,  2.5, 2, None),
    "Romanian Deadlift":      (90.0,  5.0, 2, None),
    "Incline Dumbbell Press": (30.0,  2.5, 3, None),
    "Leg Press":              (180.0, 10.0, 2, None),
    "Pull-Up":                (0.0,   2.5, 3, None),   # bodyweight + added
    "Barbell Curl":           (30.0,  2.5, 3, None),
    "Cable Tricep Pushdown":  (35.0,  2.5, 3, None),
    "Face Pull":              (25.0,  2.5, 4, None),
    "Dumbbell Lateral Raise": (10.0,  2.5, 4, None),
    "Lying Leg Curl":         (45.0,  5.0, 3, None),
    "Standing Calf Raise":    (80.0,  5.0, 2, None),
}

# Exercises that get warmup sets and heavier working sets.
MAIN_LIFTS = {
    "Barbell Bench Press", "Barbell Back Squat", "Overhead Press",
    "Barbell Row", "Romanian Deadlift",
}

PROTEIN_FOODS = [
    "Whey Protein Isolate", "Chicken Breast (raw)", "Whole Eggs",
    "Greek Yogurt (0%)", "Salmon Fillet", "Paneer", "Egg Whites",
]
CARB_FOODS = ["White Rice (cooked)", "Oats (dry)", "Banana"]


def round_to_plate(kg: float) -> float:
    """Round to the nearest 2.5kg -- real plates come in fixed sizes."""
    return round(kg / 2.5) * 2.5


def working_weight(exercise: str, week: int) -> float:
    start, inc, every, stall_after = PROGRESSION[exercise]
    effective_week = week if stall_after is None else min(week, stall_after)
    return start + inc * (effective_week // every)


def build_sets(weight: float, is_main: bool) -> list[tuple]:
    """Return [(set_number, weight_kg, reps, rpe, is_warmup), ...].

    Warmups are flagged rather than omitted, because a real logger
    records them -- and because every analytics query then has to
    remember to exclude them. That is a realistic trap to build in.
    """
    rows: list[tuple] = []
    n = 1

    if is_main and weight > 0:
        rows.append((n, round_to_plate(weight * 0.5), 8, None, True)); n += 1
        rows.append((n, round_to_plate(weight * 0.7), 5, None, True)); n += 1

    n_working = 4 if is_main else 3
    top_reps = 5 if is_main else 10

    for i in range(n_working):
        # Reps decay slightly across sets as fatigue accumulates.
        reps = max(3, top_reps - (1 if i >= 2 else 0) - random.choice([0, 0, 1]))
        rpe = min(10.0, 7.5 + i * 0.5)
        rows.append((n, weight, reps, rpe, False)); n += 1

    return rows


def main() -> None:
    url = os.getenv("DATABASE_URL")
    if not url:
        raise SystemExit("DATABASE_URL not set. Copy .env.example to .env.")

    # '+psycopg' is SQLAlchemy dialect syntax. psycopg itself does not
    # understand it, so strip it for a direct connection.
    conn_str = url.replace("+psycopg", "")

    with psycopg.connect(conn_str) as conn, conn.cursor() as cur:
        # --- clean slate -------------------------------------------
        cur.execute("DELETE FROM users WHERE lower(email) = lower(%s);", (DEMO_EMAIL,))

        cur.execute(
            """
            INSERT INTO users (email, password_hash, display_name, height_cm, units)
            VALUES (%s, %s, %s, %s, 'metric')
            RETURNING id;
            """,
            (DEMO_EMAIL, hash_password(DEMO_PASSWORD), "Demo Lifter", 178.0),
        )
        user_id = cur.fetchone()[0]

        # --- look up IDs by name, never hardcode -------------------
        cur.execute("SELECT name, id FROM exercises WHERE created_by_user_id IS NULL;")
        exercise_ids = dict(cur.fetchall())

        cur.execute("SELECT name, id FROM food_items WHERE created_by_user_id IS NULL;")
        food_ids = dict(cur.fetchall())

        # Fail loudly and EARLY if reference data is absent. The
        # tempting alternative -- skipping anything not found -- would
        # let this script report success while silently writing
        # nothing. A seed script that lies to you is worse than one
        # that crashes.
        missing = [n for n in PROGRESSION if n not in exercise_ids]
        missing += [f for f in PROTEIN_FOODS + CARB_FOODS if f not in food_ids]
        if missing:
            raise SystemExit(
                f"Reference data missing from the database: {missing}\n"
                "Run `alembic upgrade head` first."
            )

        # 8 weeks ending today, starting on a Monday.
        end = date.today()
        start = end - timedelta(days=WEEKS * 7 - 1)
        start -= timedelta(days=start.weekday())

        n_workouts = n_sets = 0

        for offset in range((end - start).days + 1):
            day = start + timedelta(days=offset)
            week = offset // 7

            # ---------- workouts ----------
            if day.weekday() in SPLIT and random.random() > 0.05:  # ~5% missed
                cur.execute(
                    "INSERT INTO workouts (user_id, performed_on) VALUES (%s, %s) RETURNING id;",
                    (user_id, day),
                )
                workout_id = cur.fetchone()[0]
                n_workouts += 1

                for order_index, name in enumerate(SPLIT[day.weekday()]):
                    cur.execute(
                        """
                        INSERT INTO workout_exercises (workout_id, exercise_id, order_index)
                        VALUES (%s, %s, %s) RETURNING id;
                        """,
                        (workout_id, exercise_ids[name], order_index),
                    )
                    we_id = cur.fetchone()[0]

                    weight = working_weight(name, week)
                    for set_number, w, reps, rpe, warmup in build_sets(
                        weight, name in MAIN_LIFTS
                    ):
                        cur.execute(
                            """
                            INSERT INTO sets
                                (workout_exercise_id, set_number, weight_kg,
                                 reps, rpe, is_warmup)
                            VALUES (%s, %s, %s, %s, %s, %s);
                            """,
                            (we_id, set_number, w, reps, rpe, warmup),
                        )
                        n_sets += 1

            # ---------- bodyweight ----------
            if random.random() > 0.15:  # skips ~15% of days, like a real person
                trend = 81.0 + 3.0 * (offset / ((end - start).days or 1))
                cur.execute(
                    """
                    INSERT INTO bodyweight_logs (user_id, measured_on, weight_kg)
                    VALUES (%s, %s, %s)
                    ON CONFLICT (user_id, measured_on) DO NOTHING;
                    """,
                    (user_id, day, round(trend + random.uniform(-0.5, 0.5), 2)),
                )

            # ---------- nutrition ----------
            weekend = day.weekday() >= 5
            protein = max(60.0, random.gauss(135 if weekend else 185, 15))
            calories = max(1500.0, random.gauss(3400 if weekend else 2950, 200))
            fat = max(30.0, random.gauss(95 if weekend else 80, 12))
            carbs = max(50.0, (calories - protein * 4 - fat * 9) / 4)

            cur.execute(
                """
                INSERT INTO nutrition_logs
                    (user_id, logged_on, calories, protein_g, carbs_g, fat_g)
                VALUES (%s, %s, %s, %s, %s, %s)
                ON CONFLICT (user_id, logged_on) DO NOTHING
                RETURNING id;
                """,
                (user_id, day, int(calories), round(protein, 2),
                 round(carbs, 2), round(fat, 2)),
            )
            row = cur.fetchone()

            if row:
                log_id = row[0]
                foods = random.sample(PROTEIN_FOODS, 3) + random.sample(CARB_FOODS, 1)
                for food in foods:
                    cur.execute(
                        """
                        INSERT INTO nutrition_entries
                            (nutrition_log_id, food_item_id, quantity_g)
                        VALUES (%s, %s, %s);
                        """,
                        (log_id, food_ids[food], round(random.uniform(80, 300), 2)),
                    )

        conn.commit()

    print(f"Seeded {n_workouts} workouts and {n_sets} sets.")
    print(f"Range: {start} to {end}")
    print("Overhead press plateaus at 60kg from week 5 onward.\n")
    print("Log in at http://localhost:8000/docs with:")
    print(f"  username: {DEMO_EMAIL}")
    print(f"  password: {DEMO_PASSWORD}")


if __name__ == "__main__":
    main()
