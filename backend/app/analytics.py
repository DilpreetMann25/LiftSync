"""Training analytics — the queries that turn logged sets into insight.

WHY THIS IS A SEPARATE MODULE
-----------------------------
Routers should handle HTTP: parse the request, call something, shape
the response. Once real logic lives inside a route it can only be
reached over HTTP, which makes it awkward to test, impossible to reuse,
and painful to call from anywhere else.

That matters concretely here: in Phase 5 the AI agent needs exactly
these numbers. It will call these functions directly rather than making
HTTP requests to your own server. Same logic, two callers.

THE FORMULA
-----------
Estimated 1RM (Epley):   e1RM = weight x (1 + reps / 30)

Raw volume is a poor progress signal: 100kg x 5 and 80kg x 10 are both
500kg but represent completely different strength. e1RM normalises any
set to a single comparable number, which is what makes session-to-
session comparison meaningful.

It degrades above ~10 reps, where it starts overestimating. Fine for
strength work; treat a 20-rep set's e1RM with suspicion.
"""

from sqlalchemy import text
from sqlalchemy.engine import Connection

# Epley, written once. Repeating this expression across three queries is
# how two of them end up disagreeing after someone "fixes" one.
E1RM = "weight_kg * (1 + reps / 30.0)"


def exercise_progression(
    conn: Connection, user_id: int, exercise_id: int, weeks: int
) -> list[dict]:
    """Session-by-session strength trend for one lift.

    Three window functions here, and the thing they share is that none
    of them collapse rows. GROUP BY turns many rows into one; a window
    function leaves every row intact and computes something using its
    neighbours.

      LAG(e1rm) OVER (ORDER BY performed_on)
          the previous session's value, so you can show the change

      AVG(e1rm) OVER (ORDER BY performed_on
                      ROWS BETWEEN 2 PRECEDING AND CURRENT ROW)
          a 3-session rolling average. The ROWS BETWEEN clause is the
          "window frame" -- literally which rows this calculation sees.

      MAX(e1rm) OVER (ORDER BY performed_on)
          the best result up to and including this row. With no frame
          clause, an ORDER BY window defaults to "everything from the
          start through the current row" -- exactly a running maximum.
    """
    rows = conn.execute(
        text(
            f"""
            WITH sessions AS (
                SELECT performed_on,
                       MAX({E1RM})    AS e1rm,
                       SUM(volume_kg) AS session_volume,
                       MAX(weight_kg) AS top_weight
                FROM v_set_details
                WHERE user_id = :user_id
                  AND exercise_id = :exercise_id
                  AND NOT is_warmup
                  AND performed_on >= CURRENT_DATE - make_interval(weeks => :weeks)
                GROUP BY performed_on
            )
            SELECT performed_on,
                   ROUND(e1rm, 1) AS e1rm,
                   ROUND(AVG(e1rm) OVER (
                       ORDER BY performed_on
                       ROWS BETWEEN 2 PRECEDING AND CURRENT ROW
                   ), 1) AS rolling_e1rm,
                   ROUND(e1rm - LAG(e1rm) OVER (ORDER BY performed_on), 1)
                       AS change_from_previous,
                   ROUND(MAX(e1rm) OVER (ORDER BY performed_on), 1)
                       AS best_e1rm_to_date,
                   session_volume,
                   top_weight
            FROM sessions
            ORDER BY performed_on;
            """
        ),
        {"user_id": user_id, "exercise_id": exercise_id, "weeks": weeks},
    ).mappings().all()

    return [dict(row) for row in rows]


def detect_plateaus(
    conn: Connection,
    user_id: int,
    stall_weeks: int = 3,
    lookback_weeks: int = 26,
    min_recent_sessions: int = 3,
) -> list[dict]:
    """Find lifts that have stopped progressing.

    THE DEFINITION
    --------------
    A lift is plateaued when its best e1RM in the recent window is no
    higher than its best e1RM before that. Plain English: you have not
    hit a new best in N weeks.

    Chosen over slope-based alternatives because it is explainable in
    one sentence. A user told "your overhead press hasn't improved in
    3 weeks" understands immediately; "your regression coefficient is
    0.02" helps nobody.

    THE WINDOW IS NOT THE SAME FOR EVERY LIFT
    -----------------------------------------
    The first version of this used one threshold for everything, and
    flagged Face Pull and Dumbbell Lateral Raise on real data -- both
    of which were progressing exactly on schedule, just slowly.

    Compound lifts progress in small, frequent jumps: a stalled squat
    is visible within three weeks. Isolation work moves in larger,
    rarer steps -- going 10kg to 12.5kg on a lateral raise is a 25%
    jump, and monthly is normal. Judging both by the same clock
    guarantees the slowest-progressing lifts get flagged the most,
    which is exactly backwards.

    So isolation movements get double the window.

    THE GUARDS MATTER AS MUCH AS THE RULE
    -------------------------------------
    min_recent_sessions -- without it, an exercise trained once two
      months ago is "plateaued", which is noise, not insight.

    previous_best IS NOT NULL -- a lift started last week has no
      history to compare against. Not plateaued; just new.

    lookback_weeks -- bounds the comparison. Otherwise a PR from two
      years ago would mark you permanently stalled.

    False positives destroy trust in a feature like this. Better to
    stay quiet when unsure than to nag about a lift that is fine.
    """
    rows = conn.execute(
        text(
            f"""
            WITH session_e1rm AS (
                SELECT exercise_id,
                       exercise_name,
                       category,
                       performed_on,
                       MAX({E1RM}) AS e1rm
                FROM v_set_details
                WHERE user_id = :user_id
                  AND NOT is_warmup
                  AND performed_on >= CURRENT_DATE
                                      - make_interval(weeks => :lookback_weeks)
                GROUP BY exercise_id, exercise_name, category, performed_on
            ),

            -- Attach each exercise's own stall window. Computing it as
            -- a column keeps the rule in one place instead of repeating
            -- a CASE inside all three FILTER clauses below.
            scoped AS (
                SELECT se.*,
                       CASE WHEN se.category = 'compound'
                            THEN CAST(:stall_weeks AS int)
                            ELSE CAST(:stall_weeks AS int) * 2
                       END AS stall_weeks
                FROM session_e1rm se
            ),

            -- DISTINCT ON is a Postgres speciality: keep the first row
            -- per exercise_id after sorting. Sorted by e1rm DESC then
            -- date ASC, "first" means the best session, and the
            -- EARLIEST date if that best was matched more than once --
            -- which is what you want, since re-hitting an old best is
            -- not a new PR.
            personal_best AS (
                SELECT DISTINCT ON (exercise_id)
                       exercise_id,
                       e1rm         AS best_e1rm,
                       performed_on AS best_achieved_on
                FROM scoped
                ORDER BY exercise_id, e1rm DESC, performed_on ASC
            ),

            -- FILTER splits each exercise's history into "recent" and
            -- "before that" in a single pass, instead of joining the
            -- table to itself. Note the boundary now comes from the
            -- row's own stall_weeks, so it differs per exercise.
            windows AS (
                SELECT exercise_id,
                       exercise_name,
                       category,
                       stall_weeks,
                       MAX(e1rm) FILTER (
                           WHERE performed_on >= CURRENT_DATE
                                                 - make_interval(weeks => stall_weeks)
                       ) AS recent_best,
                       MAX(e1rm) FILTER (
                           WHERE performed_on < CURRENT_DATE
                                                - make_interval(weeks => stall_weeks)
                       ) AS previous_best,
                       COUNT(*) FILTER (
                           WHERE performed_on >= CURRENT_DATE
                                                 - make_interval(weeks => stall_weeks)
                       ) AS recent_sessions,
                       MAX(performed_on) AS last_trained_on
                FROM scoped
                GROUP BY exercise_id, exercise_name, category, stall_weeks
            )

            SELECT w.exercise_id,
                   w.exercise_name,
                   w.category::text          AS category,
                   w.stall_weeks             AS stall_weeks_applied,
                   ROUND(pb.best_e1rm, 1)    AS best_e1rm,
                   pb.best_achieved_on,
                   ROUND((CURRENT_DATE - pb.best_achieved_on) / 7.0, 1)
                       AS weeks_since_best,
                   ROUND(w.recent_best, 1)   AS recent_best_e1rm,
                   w.recent_sessions,
                   w.last_trained_on
            FROM windows w
            JOIN personal_best pb ON pb.exercise_id = w.exercise_id
            WHERE w.previous_best IS NOT NULL
              AND w.recent_best IS NOT NULL
              AND w.recent_sessions >= :min_recent_sessions
              AND w.recent_best <= w.previous_best
            ORDER BY weeks_since_best DESC;
            """
        ),
        {
            "user_id": user_id,
            "stall_weeks": stall_weeks,
            "lookback_weeks": lookback_weeks,
            "min_recent_sessions": min_recent_sessions,
        },
    ).mappings().all()

    return [dict(row) for row in rows]


def weekly_muscle_volume(
    conn: Connection, user_id: int, weeks: int, muscle_group: str | None = None
) -> list[dict]:
    """Weighted training volume per muscle group per week.

    SUM(volume_kg * contribution) is the point. A bench press set
    contributes 100% to chest but only 40% to front delts, so a
    "shoulder volume" figure that counted bench fully would be wrong.

    PARTIAL WEEKS ARE EXCLUDED. date_trunc snaps dates to Monday, so
    the current week is almost always incomplete and shows up as a
    dramatic collapse in volume. You found this bug by eye in Phase 1;
    the `< date_trunc('week', CURRENT_DATE)` filter is the fix.
    """
    rows = conn.execute(
        text(
            """
            SELECT date_trunc('week', s.performed_on)::date AS week,
                   m.name                                   AS muscle_group,
                   ROUND(SUM(s.volume_kg * emg.contribution), 1) AS weighted_volume,
                   COUNT(*)                                 AS working_sets
            FROM v_set_details s
            JOIN exercise_muscle_groups emg ON emg.exercise_id = s.exercise_id
            JOIN muscle_groups m            ON m.id = emg.muscle_group_id
            WHERE s.user_id = :user_id
              AND NOT s.is_warmup
              AND s.performed_on >= date_trunc('week', CURRENT_DATE)
                                    - make_interval(weeks => :weeks)
              AND s.performed_on <  date_trunc('week', CURRENT_DATE)
              AND (:muscle_group IS NULL OR m.name = :muscle_group)
            GROUP BY week, m.name
            ORDER BY week, m.name;
            """
        ),
        {"user_id": user_id, "weeks": weeks, "muscle_group": muscle_group},
    ).mappings().all()

    return [dict(row) for row in rows]
