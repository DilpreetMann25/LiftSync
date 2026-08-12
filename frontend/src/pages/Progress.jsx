/** Per-exercise strength trend: e1RM over time, with the raw sessions behind it. */

import { useEffect, useMemo, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { api } from "../lib/api";
import { useApi } from "../lib/useApi";
import { delta, fullDate, kg, shortDate, volume } from "../lib/format";
import { ProgressionChart } from "../components/charts";
import {
  Badge,
  Card,
  CardHeader,
  EmptyState,
  ErrorState,
  PageHeader,
  Select,
  Skeleton,
  Stat,
} from "../components/ui";

const WINDOWS = [
  { value: 4, label: "4 weeks" },
  { value: 8, label: "8 weeks" },
  { value: 12, label: "12 weeks" },
  { value: 26, label: "6 months" },
  { value: 52, label: "1 year" },
];

export default function Progress() {
  // Exercise lives in the URL, so a chart can be linked to directly --
  // which is what the dashboard's "View trend" button relies on.
  const [searchParams, setSearchParams] = useSearchParams();
  const [weeks, setWeeks] = useState(12);

  const exercises = useApi(() => api.exercises(), []);
  const exerciseId = searchParams.get("exercise");

  // Default to the first compound lift once the list arrives, rather
  // than showing an empty chart and making the user choose.
  useEffect(() => {
    if (!exerciseId && exercises.data?.length) {
      const preferred =
        exercises.data.find((e) => e.name === "Barbell Bench Press") ||
        exercises.data.find((e) => e.category === "compound") ||
        exercises.data[0];
      setSearchParams({ exercise: String(preferred.id) }, { replace: true });
    }
  }, [exercises.data, exerciseId, setSearchParams]);

  const progression = useApi(
    () => api.progression(exerciseId, weeks),
    [exerciseId, weeks],
    { skip: !exerciseId }
  );

  const selected = exercises.data?.find((e) => String(e.id) === String(exerciseId));

  const chartData = useMemo(
    () =>
      (progression.data || []).map((point) => ({
        ...point,
        label: shortDate(point.performed_on),
      })),
    [progression.data]
  );

  const summary = useMemo(() => {
    if (!progression.data?.length) return null;

    const points = progression.data;
    const first = points[0];
    const last = points[points.length - 1];
    const best = points.reduce((a, b) => (b.e1rm > a.e1rm ? b : a));

    return {
      current: last.e1rm,
      change: last.e1rm - first.e1rm,
      // Guard against a single-session history, where percentage
      // change would divide by a first value equal to the last.
      percent: first.e1rm ? ((last.e1rm - first.e1rm) / first.e1rm) * 100 : 0,
      best: best.e1rm,
      bestOn: best.performed_on,
      sessions: points.length,
    };
  }, [progression.data]);

  return (
    <div className="animate-fade-up">
      <PageHeader
        title="Progress"
        description="Estimated 1RM per session, smoothed against week-to-week noise."
      />

      <div className="mb-6 grid gap-3 sm:grid-cols-2 lg:max-w-xl">
        <Select
          label="Exercise"
          value={exerciseId || ""}
          onChange={(e) => setSearchParams({ exercise: e.target.value })}
          disabled={exercises.loading}
        >
          {exercises.data?.map((exercise) => (
            <option key={exercise.id} value={exercise.id}>
              {exercise.name}
            </option>
          ))}
        </Select>

        <Select
          label="Window"
          value={weeks}
          onChange={(e) => setWeeks(Number(e.target.value))}
        >
          {WINDOWS.map((w) => (
            <option key={w.value} value={w.value}>
              {w.label}
            </option>
          ))}
        </Select>
      </div>

      {progression.loading ? (
        <div className="space-y-6">
          <Skeleton className="h-24 w-full" />
          <Skeleton className="h-80 w-full" />
        </div>
      ) : progression.error ? (
        <Card>
          {/* 404 here means "no data in this window", which is not an
              error worth alarming anyone about -- so it gets an empty
              state rather than a red one. */}
          {progression.error.status === 404 ? (
            <EmptyState
              title="Nothing logged in this window"
              description={`No ${selected?.name || "sessions"} recorded in the last ${weeks} weeks. Try a longer window.`}
            />
          ) : (
            <ErrorState error={progression.error} onRetry={progression.refresh} />
          )}
        </Card>
      ) : (
        <>
          {summary && (
            <div className="mb-6 grid grid-cols-2 gap-3 lg:grid-cols-4">
              <Card>
                <Stat label="Current e1RM" value={summary.current.toFixed(1)} unit="kg" />
              </Card>
              <Card>
                <Stat
                  label="Change"
                  value={delta(summary.change)}
                  unit="kg"
                  tone={summary.change > 0 ? "accent" : summary.change < 0 ? "danger" : "default"}
                  delta={`${delta(summary.percent, "%")} over ${weeks} weeks`}
                />
              </Card>
              <Card>
                <Stat
                  label="Best"
                  value={summary.best.toFixed(1)}
                  unit="kg"
                  delta={fullDate(summary.bestOn)}
                />
              </Card>
              <Card>
                <Stat label="Sessions" value={summary.sessions} />
              </Card>
            </div>
          )}

          <Card className="mb-6">
            <CardHeader
              title={selected?.name || "Progression"}
              subtitle="Solid line is each session · dashed line is the 3-session average"
              action={selected && <Badge>{selected.category}</Badge>}
            />
            {chartData.length ? (
              <ProgressionChart data={chartData} height={300} />
            ) : (
              <EmptyState title="No sessions in this window" />
            )}
          </Card>

          <Card padded={false}>
            <div className="p-5">
              <CardHeader title="Session detail" subtitle="Working sets only" />
            </div>

            {progression.data?.length ? (
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="border-y border-ink-800 text-left text-[11px] uppercase tracking-widest text-ink-400">
                      <th className="px-5 py-2.5 font-medium">Date</th>
                      <th className="px-5 py-2.5 text-right font-medium">Top set</th>
                      <th className="px-5 py-2.5 text-right font-medium">e1RM</th>
                      <th className="px-5 py-2.5 text-right font-medium">Change</th>
                      <th className="px-5 py-2.5 text-right font-medium">Volume</th>
                    </tr>
                  </thead>
                  <tbody>
                    {[...progression.data].reverse().map((point) => {
                      const isPR = point.e1rm >= point.best_e1rm_to_date;
                      return (
                        <tr
                          key={point.performed_on}
                          className="border-b border-ink-850 transition-colors last:border-0 hover:bg-ink-850"
                        >
                          <td className="px-5 py-3 text-ink-200">
                            <span className="flex items-center gap-2">
                              {fullDate(point.performed_on)}
                              {/* A running-max comparison, so this marks
                                  the session that set the record rather
                                  than every session at that weight. */}
                              {isPR && <Badge tone="accent">PR</Badge>}
                            </span>
                          </td>
                          <td className="tnum px-5 py-3 text-right text-ink-300">
                            {kg(point.top_weight)}
                          </td>
                          <td className="tnum px-5 py-3 text-right font-medium text-ink-100">
                            {point.e1rm.toFixed(1)}
                          </td>
                          <td
                            className={`tnum px-5 py-3 text-right ${
                              point.change_from_previous > 0
                                ? "text-accent"
                                : point.change_from_previous < 0
                                  ? "text-danger"
                                  : "text-ink-400"
                            }`}
                          >
                            {point.change_from_previous === null
                              ? "—"
                              : delta(point.change_from_previous)}
                          </td>
                          <td className="tnum px-5 py-3 text-right text-ink-300">
                            {volume(point.session_volume)}
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            ) : (
              <EmptyState title="No sessions to show" />
            )}
          </Card>
        </>
      )}
    </div>
  );
}
