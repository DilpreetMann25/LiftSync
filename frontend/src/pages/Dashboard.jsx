/** The screen that opens on sign-in: what needs attention, and how training is going. */

import { useMemo } from "react";
import { Link } from "react-router-dom";
import { api } from "../lib/api";
import { useApi } from "../lib/useApi";
import { useAuth } from "../context/AuthContext";
import { fullDate, kg, muscleLabel, relativeDays, shortDate, volume } from "../lib/format";
import { VolumeBarChart } from "../components/charts";
import {
  Badge,
  Button,
  Card,
  CardHeader,
  EmptyState,
  ErrorState,
  PageHeader,
  Skeleton,
  Stat,
} from "../components/ui";

export default function Dashboard() {
  const { user } = useAuth();

  const plateaus = useApi(() => api.plateaus(3), []);
  const workouts = useApi(() => api.workouts(10), []);
  const muscleVolume = useApi(() => api.muscleVolume(8), []);

  /**
   * Roll weekly per-muscle rows up into a total per week.
   *
   * useMemo so this only recomputes when the data changes, rather
   * than on every render. Cheap here, but the habit matters once a
   * component re-renders on every keystroke.
   */
  const weeklyTotals = useMemo(() => {
    if (!muscleVolume.data) return [];

    const byWeek = new Map();
    for (const row of muscleVolume.data) {
      byWeek.set(row.week, (byWeek.get(row.week) || 0) + Number(row.weighted_volume));
    }

    return [...byWeek.entries()]
      .sort(([a], [b]) => a.localeCompare(b))
      .map(([week, value]) => ({ label: shortDate(week), value: Math.round(value) }));
  }, [muscleVolume.data]);

  const topMuscles = useMemo(() => {
    if (!muscleVolume.data?.length) return [];

    const weeks = [...new Set(muscleVolume.data.map((r) => r.week))].sort();
    const latest = weeks[weeks.length - 1];

    return muscleVolume.data
      .filter((row) => row.week === latest)
      .sort((a, b) => b.weighted_volume - a.weighted_volume)
      .slice(0, 6);
  }, [muscleVolume.data]);

  const totalVolume = workouts.data?.reduce(
    (sum, w) => sum + Number(w.total_volume_kg),
    0
  );

  return (
    <div className="animate-fade-up">
      <PageHeader
        title={`Welcome back, ${user?.display_name?.split(" ")[0] || "lifter"}`}
        description="Here's what your training data says today."
        action={
          <Link to="/log">
            <Button size="md">Log a workout</Button>
          </Link>
        }
      />

      {/* ---------- headline numbers ---------- */}
      <div className="mb-6 grid grid-cols-2 gap-3 lg:grid-cols-4">
        <Card>
          <Stat
            label="Sessions"
            value={workouts.loading ? "—" : (workouts.data?.length ?? 0)}
            unit="last 10"
          />
        </Card>
        <Card>
          <Stat
            label="Volume"
            value={workouts.loading ? "—" : volume(totalVolume)}
            unit="kg"
          />
        </Card>
        <Card>
          <Stat
            label="Plateaus"
            value={plateaus.loading ? "—" : (plateaus.data?.length ?? 0)}
            tone={plateaus.data?.length ? "warn" : "accent"}
          />
        </Card>
        <Card>
          <Stat
            label="Last session"
            value={
              workouts.loading
                ? "—"
                : workouts.data?.[0]
                  ? relativeDays(workouts.data[0].performed_on)
                  : "never"
            }
          />
        </Card>
      </div>

      {/* ---------- plateau alerts ----------
          Placed first and given the most visual weight, because it is
          the only thing on this page that asks the user to act. */}
      <Card className="mb-6">
        <CardHeader
          title="Plateau watch"
          subtitle="Lifts with no new best in the last 3 weeks"
          action={
            <Link to="/coach">
              <Button variant="secondary" size="sm">
                Ask the coach
              </Button>
            </Link>
          }
        />

        {plateaus.loading ? (
          <div className="space-y-2">
            <Skeleton className="h-16 w-full" />
            <Skeleton className="h-16 w-full" />
          </div>
        ) : plateaus.error ? (
          <ErrorState error={plateaus.error} onRetry={plateaus.refresh} />
        ) : plateaus.data?.length ? (
          <div className="space-y-2">
            {plateaus.data.map((p) => (
              <div
                key={p.exercise_id}
                className="flex flex-wrap items-center gap-4 rounded-lg border border-warn/20 bg-warn/[0.04] p-4"
              >
                <div className="min-w-0 flex-1">
                  <div className="flex flex-wrap items-center gap-2">
                    <span className="text-sm font-medium text-ink-100">
                      {p.exercise_name}
                    </span>
                    <Badge tone="warn">
                      {p.weeks_since_best}w since best
                    </Badge>
                    <Badge>{p.category}</Badge>
                  </div>
                  <p className="mt-1 text-xs text-ink-400">
                    Best {kg(p.best_e1rm)} e1RM on {fullDate(p.best_achieved_on)} ·{" "}
                    {p.recent_sessions} sessions since · judged on a{" "}
                    {p.stall_weeks_applied}-week window
                  </p>
                </div>
                <Link to={`/progress?exercise=${p.exercise_id}`}>
                  <Button variant="ghost" size="sm">
                    View trend →
                  </Button>
                </Link>
              </div>
            ))}
          </div>
        ) : (
          <EmptyState
            title="Everything is moving"
            description="No lift has gone three weeks without a new best. Keep going."
          />
        )}
      </Card>

      <div className="grid gap-6 lg:grid-cols-3">
        {/* ---------- weekly volume ---------- */}
        <Card className="lg:col-span-2">
          <CardHeader
            title="Weekly training volume"
            subtitle="Weighted by muscle contribution · current week excluded"
          />
          {muscleVolume.loading ? (
            <Skeleton className="h-60 w-full" />
          ) : muscleVolume.error ? (
            <ErrorState error={muscleVolume.error} onRetry={muscleVolume.refresh} />
          ) : weeklyTotals.length ? (
            <VolumeBarChart data={weeklyTotals} formatter={(v) => `${volume(v)} kg`} />
          ) : (
            <EmptyState
              title="No volume yet"
              description="Log a few sessions and this fills in."
            />
          )}
        </Card>

        {/* ---------- muscle split ---------- */}
        <Card>
          <CardHeader title="Last full week" subtitle="Volume by muscle group" />
          {muscleVolume.loading ? (
            <Skeleton className="h-60 w-full" />
          ) : topMuscles.length ? (
            <div className="space-y-3">
              {topMuscles.map((row, index) => {
                const max = Number(topMuscles[0].weighted_volume);
                const pct = (Number(row.weighted_volume) / max) * 100;
                return (
                  <div key={row.muscle_group}>
                    <div className="mb-1 flex items-baseline justify-between text-xs">
                      <span className="text-ink-300">{muscleLabel(row.muscle_group)}</span>
                      <span className="tnum text-ink-400">
                        {volume(row.weighted_volume)} kg
                      </span>
                    </div>
                    <div className="h-1.5 overflow-hidden rounded-full bg-ink-800">
                      <div
                        className="h-full rounded-full bg-accent transition-all"
                        style={{
                          width: `${pct}%`,
                          // Fade the bars down the list so the eye
                          // reads the ranking without extra labels.
                          opacity: 1 - index * 0.12,
                        }}
                      />
                    </div>
                  </div>
                );
              })}
            </div>
          ) : (
            <EmptyState title="Nothing logged yet" />
          )}
        </Card>
      </div>

      {/* ---------- recent sessions ---------- */}
      <Card className="mt-6" padded={false}>
        <div className="p-5">
          <CardHeader title="Recent sessions" subtitle="Your last 10 workouts" />
        </div>

        {workouts.loading ? (
          <div className="space-y-2 px-5 pb-5">
            <Skeleton className="h-12 w-full" />
            <Skeleton className="h-12 w-full" />
            <Skeleton className="h-12 w-full" />
          </div>
        ) : workouts.data?.length ? (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-y border-ink-800 text-left text-[11px] uppercase tracking-widest text-ink-400">
                  <th className="px-5 py-2.5 font-medium">Date</th>
                  <th className="px-5 py-2.5 font-medium">Exercises</th>
                  <th className="px-5 py-2.5 font-medium">Sets</th>
                  <th className="px-5 py-2.5 text-right font-medium">Volume</th>
                </tr>
              </thead>
              <tbody>
                {workouts.data.map((w) => (
                  <tr
                    key={w.id}
                    className="border-b border-ink-850 transition-colors last:border-0 hover:bg-ink-850"
                  >
                    <td className="px-5 py-3">
                      <div className="text-ink-200">{fullDate(w.performed_on)}</div>
                      <div className="text-[11px] text-ink-400">
                        {relativeDays(w.performed_on)}
                      </div>
                    </td>
                    <td className="tnum px-5 py-3 text-ink-300">{w.exercise_count}</td>
                    <td className="tnum px-5 py-3 text-ink-300">{w.set_count}</td>
                    <td className="tnum px-5 py-3 text-right font-medium text-ink-100">
                      {volume(w.total_volume_kg)} kg
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <EmptyState
            title="No workouts yet"
            description="Log your first session to start building a history."
            action={
              <Link to="/log">
                <Button size="sm">Log a workout</Button>
              </Link>
            }
          />
        )}
      </Card>
    </div>
  );
}
