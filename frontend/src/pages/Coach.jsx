/**
 * The AI coach.
 *
 * Two things this screen has to do that a normal page does not:
 *
 *   1. Hold attention through a 10-30 second wait. A bare spinner
 *      reads as "broken" at that length, so the investigation steps
 *      are surfaced as they would plausibly happen.
 *   2. Show its work. The tools the agent chose are displayed
 *      alongside the answer -- that is the difference between a black
 *      box and something a user can judge.
 */

import { useEffect, useState } from "react";
import { api } from "../lib/api";
import {
  Badge,
  Button,
  Card,
  CardHeader,
  EmptyState,
  PageHeader,
  Spinner,
} from "../components/ui";

const SUGGESTIONS = [
  "I'm plateauing on my overhead press at 60kg. What should I do?",
  "Is my shoulder volume too low, or is recovery the problem?",
  "My bench is climbing but my squat has stalled. Why?",
  "Am I eating enough to keep making progress?",
];

/** Rough plain-English labels for the tool names the API returns. */
const TOOL_LABELS = {
  detect_plateaus: "Checked for stalled lifts",
  exercise_progression: "Read session-by-session strength history",
  muscle_group_volume: "Analysed muscle group volume",
  nutrition_summary: "Reviewed calories and macros",
  bodyweight_trend: "Checked bodyweight trend",
  list_available_exercises: "Looked up your exercise library",
};

const STAGES = [
  "Reading your training history…",
  "Checking which lifts have stalled…",
  "Comparing volume against progress…",
  "Reviewing nutrition and bodyweight…",
  "Writing your programme…",
];

export default function Coach() {
  const [question, setQuestion] = useState("");
  const [result, setResult] = useState(null);
  const [error, setError] = useState(null);
  const [loading, setLoading] = useState(false);
  const [stage, setStage] = useState(0);

  // Advance the stage text while waiting. Purely cosmetic -- it does
  // not track what the agent is really doing -- but a static message
  // for thirty seconds makes people reload the page.
  useEffect(() => {
    if (!loading) return;
    setStage(0);
    const timer = setInterval(
      () => setStage((s) => Math.min(s + 1, STAGES.length - 1)),
      4500
    );
    return () => clearInterval(timer);
  }, [loading]);

  async function ask(text) {
    const q = (text ?? question).trim();
    if (q.length < 5) return;

    setQuestion(q);
    setError(null);
    setResult(null);
    setLoading(true);

    try {
      setResult(await api.askCoach(q));
    } catch (err) {
      setError(err);
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="animate-fade-up">
      <PageHeader
        title="AI Coach"
        description="Asks your database what's actually happening, then programmes around it."
      />

      <Card className="mb-6">
        <div className="flex flex-col gap-3 sm:flex-row">
          <input
            value={question}
            onChange={(e) => setQuestion(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && !loading && ask()}
            placeholder="Ask about a plateau, your volume, your nutrition…"
            className="flex-1 rounded-lg border border-ink-700 bg-ink-850 px-4 py-3 text-sm placeholder-ink-400 focus:border-accent focus:outline-none"
            disabled={loading}
          />
          <Button size="lg" onClick={() => ask()} loading={loading} disabled={question.trim().length < 5}>
            {loading ? "Thinking…" : "Ask coach"}
          </Button>
        </div>

        {!result && !loading && (
          <div className="mt-4">
            <div className="mb-2 text-[11px] uppercase tracking-widest text-ink-400">
              Try asking
            </div>
            <div className="flex flex-wrap gap-2">
              {SUGGESTIONS.map((s) => (
                <button
                  key={s}
                  onClick={() => ask(s)}
                  className="rounded-full border border-ink-700 bg-ink-850 px-3 py-1.5 text-xs text-ink-300 transition-colors hover:border-accent/40 hover:text-ink-100"
                >
                  {s}
                </button>
              ))}
            </div>
          </div>
        )}
      </Card>

      {loading && (
        <Card>
          <div className="flex flex-col items-center justify-center py-12">
            <div className="mb-5 flex h-12 w-12 items-center justify-center rounded-full bg-accent/10 animate-pulse-ring">
              <Spinner size={22} className="text-accent" />
            </div>
            <p className="text-sm font-medium text-ink-200">{STAGES[stage]}</p>
            <p className="mt-1.5 max-w-sm text-center text-xs text-ink-400">
              The coach is querying your training data directly. This usually takes
              10–30 seconds.
            </p>
          </div>
        </Card>
      )}

      {error && (
        <Card>
          <EmptyState
            title={error.status === 503 ? "Coach not configured" : "The coach is unavailable"}
            description={
              error.status === 503
                ? "Add a GEMINI_API_KEY to your .env and restart the backend."
                : error.message
            }
            action={
              <Button variant="secondary" size="sm" onClick={() => ask(question)}>
                Try again
              </Button>
            }
          />
        </Card>
      )}

      {result && (
        <div className="space-y-5 animate-fade-up">
          {/* ---------- what it concluded ---------- */}
          <Card>
            <div className="flex items-start gap-3">
              <div className="mt-0.5 flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-accent/10 text-accent">
                <svg width="16" height="16" viewBox="0 0 24 24" fill="none">
                  <path
                    d="M12 3l1.9 5.1L19 10l-5.1 1.9L12 17l-1.9-5.1L5 10l5.1-1.9L12 3Z"
                    stroke="currentColor"
                    strokeWidth="1.6"
                    strokeLinejoin="round"
                  />
                </svg>
              </div>
              <div className="min-w-0 flex-1">
                <h2 className="text-sm font-semibold text-ink-100">
                  {result.program.diagnosis}
                </h2>
                <p className="mt-2 text-sm leading-relaxed text-ink-300">
                  {result.program.reasoning}
                </p>
                {result.program.target_exercise && (
                  <Badge tone="accent" className="mt-3">
                    Target: {result.program.target_exercise}
                  </Badge>
                )}
              </div>
            </div>
          </Card>

          {/* ---------- how it got there ----------
              Shown, not hidden. An agent that cannot be inspected is
              one the user has to take on faith. */}
          <Card>
            <CardHeader
              title="How it investigated"
              subtitle={`${result.tools_used.length} database queries · ${result.model}`}
            />
            <div className="space-y-2">
              {result.tools_used.map((tool, index) => (
                <div key={`${tool}-${index}`} className="flex items-center gap-3 text-xs">
                  <span className="tnum flex h-5 w-5 items-center justify-center rounded bg-ink-800 text-[10px] text-ink-400">
                    {index + 1}
                  </span>
                  <span className="text-ink-300">{TOOL_LABELS[tool] || tool}</span>
                  <code className="ml-auto rounded bg-ink-850 px-1.5 py-0.5 text-[10px] text-ink-400">
                    {tool}
                  </code>
                </div>
              ))}
            </div>
            <div className="mt-4 border-t border-ink-800 pt-3 text-[11px] text-ink-400">
              {result.input_tokens.toLocaleString()} input ·{" "}
              {result.output_tokens.toLocaleString()} output tokens
            </div>
          </Card>

          {/* ---------- the programme ---------- */}
          <div>
            <h2 className="mb-3 text-sm font-semibold text-ink-100">
              Your 4-week block
            </h2>
            <div className="grid gap-4 lg:grid-cols-2">
              {result.program.weeks.map((week) => (
                <Card key={week.week_number}>
                  <div className="mb-4 flex items-center gap-2.5">
                    <span className="tnum flex h-7 w-7 items-center justify-center rounded-lg bg-accent/10 text-xs font-semibold text-accent">
                      {week.week_number}
                    </span>
                    <div>
                      <div className="text-sm font-medium text-ink-100">{week.focus}</div>
                      <div className="text-[11px] text-ink-400">
                        Week {week.week_number}
                      </div>
                    </div>
                  </div>

                  <div className="space-y-3">
                    {week.exercises.map((exercise, i) => (
                      <div
                        key={i}
                        className="rounded-lg border border-ink-800 bg-ink-850 p-3"
                      >
                        <div className="flex flex-wrap items-baseline justify-between gap-2">
                          <span className="text-sm text-ink-100">
                            {exercise.exercise_name}
                          </span>
                          <span className="tnum text-xs text-accent">
                            {exercise.sets} × {exercise.reps}
                          </span>
                        </div>
                        <div className="mt-1 text-xs text-ink-400">
                          {exercise.intensity}
                        </div>
                        {exercise.notes && (
                          <div className="mt-1.5 text-xs italic leading-relaxed text-ink-400">
                            {exercise.notes}
                          </div>
                        )}
                      </div>
                    ))}
                  </div>
                </Card>
              ))}
            </div>
          </div>

          {result.program.nutrition_note && (
            <Card>
              <CardHeader title="Nutrition" />
              <p className="text-sm leading-relaxed text-ink-300">
                {result.program.nutrition_note}
              </p>
            </Card>
          )}

          <p className="pb-4 text-center text-[11px] text-ink-400">
            Generated from your logged data. Not medical advice — see a professional
            for pain or injury.
          </p>
        </div>
      )}
    </div>
  );
}
