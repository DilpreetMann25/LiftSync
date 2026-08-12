/**
 * Workout logger.
 *
 * Design constraint that shaped everything here: this gets used
 * standing in a gym, one-handed, between sets. So new sets copy the
 * previous set's weight and reps (you usually repeat them), controls
 * are large enough to hit without aiming, and the running volume
 * total updates as you type.
 */

import { useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import { api } from "../lib/api";
import { useApi } from "../lib/useApi";
import { volume } from "../lib/format";
import {
  Badge,
  Button,
  Card,
  CardHeader,
  EmptyState,
  Input,
  PageHeader,
  Select,
  Skeleton,
} from "../components/ui";

const today = () => new Date().toISOString().slice(0, 10);

const emptySet = (previous) => ({
  // Carry the last set forward: straight sets are the common case, so
  // repeating them should take zero taps.
  weight_kg: previous?.weight_kg ?? "",
  reps: previous?.reps ?? "",
  rpe: "",
  is_warmup: false,
});

export default function LogWorkout() {
  const navigate = useNavigate();
  const exercises = useApi(() => api.exercises(), []);

  const [performedOn, setPerformedOn] = useState(today());
  const [notes, setNotes] = useState("");
  const [blocks, setBlocks] = useState([]);
  const [picker, setPicker] = useState("");
  const [error, setError] = useState(null);
  const [saving, setSaving] = useState(false);

  function addExercise(id) {
    const exercise = exercises.data?.find((e) => String(e.id) === String(id));
    if (!exercise) return;

    setBlocks((prev) => [
      ...prev,
      { key: crypto.randomUUID(), exercise, sets: [emptySet()] },
    ]);
    setPicker("");
  }

  // All these updaters build new arrays rather than mutating. React
  // decides whether to re-render by comparing references, so pushing
  // into an existing array would change the data without the screen
  // ever updating.
  const updateSet = (blockKey, index, field, value) =>
    setBlocks((prev) =>
      prev.map((block) =>
        block.key !== blockKey
          ? block
          : {
              ...block,
              sets: block.sets.map((set, i) =>
                i === index ? { ...set, [field]: value } : set
              ),
            }
      )
    );

  const addSet = (blockKey) =>
    setBlocks((prev) =>
      prev.map((block) =>
        block.key !== blockKey
          ? block
          : { ...block, sets: [...block.sets, emptySet(block.sets.at(-1))] }
      )
    );

  const removeSet = (blockKey, index) =>
    setBlocks((prev) =>
      prev.map((block) =>
        block.key !== blockKey
          ? block
          : { ...block, sets: block.sets.filter((_, i) => i !== index) }
      )
    );

  const removeBlock = (blockKey) =>
    setBlocks((prev) => prev.filter((block) => block.key !== blockKey));

  /** Working-set volume, matching how the backend computes it. */
  const totalVolume = useMemo(
    () =>
      blocks.reduce(
        (sum, block) =>
          sum +
          block.sets.reduce(
            (blockSum, set) =>
              set.is_warmup
                ? blockSum
                : blockSum + (Number(set.weight_kg) || 0) * (Number(set.reps) || 0),
            0
          ),
        0
      ),
    [blocks]
  );

  const workingSets = blocks.reduce(
    (n, block) => n + block.sets.filter((s) => !s.is_warmup).length,
    0
  );

  async function save() {
    setError(null);

    // Drop incomplete sets rather than sending them. The API would
    // reject reps: 0 with a 422, and "you left a row blank" is not
    // worth surfacing as a validation failure.
    const payload = {
      performed_on: performedOn,
      notes: notes || null,
      exercises: blocks
        .map((block) => ({
          exercise_id: block.exercise.id,
          sets: block.sets
            .filter((set) => Number(set.weight_kg) >= 0 && Number(set.reps) > 0)
            .map((set) => ({
              weight_kg: Number(set.weight_kg),
              reps: Number(set.reps),
              rpe: set.rpe ? Number(set.rpe) : null,
              is_warmup: set.is_warmup,
            })),
        }))
        .filter((block) => block.sets.length > 0),
    };

    if (!payload.exercises.length) {
      setError("Add at least one exercise with a completed set.");
      return;
    }

    setSaving(true);
    try {
      await api.createWorkout(payload);
      navigate("/");
    } catch (err) {
      setError(err.message);
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="animate-fade-up">
      <PageHeader
        title="Log a workout"
        description="Add exercises in the order you performed them."
        action={
          <div className="flex items-center gap-3">
            <div className="text-right">
              <div className="text-[11px] uppercase tracking-widest text-ink-400">
                Volume
              </div>
              <div className="tnum text-lg font-semibold text-accent">
                {volume(totalVolume)} kg
              </div>
            </div>
            <Button size="lg" onClick={save} loading={saving} disabled={!workingSets}>
              Save workout
            </Button>
          </div>
        }
      />

      <Card className="mb-5">
        <div className="grid gap-4 sm:grid-cols-2">
          <Input
            label="Date"
            type="date"
            value={performedOn}
            onChange={(e) => setPerformedOn(e.target.value)}
            max={today()}
          />
          <Input
            label="Notes"
            value={notes}
            onChange={(e) => setNotes(e.target.value)}
            placeholder="Felt strong, slept well…"
          />
        </div>
      </Card>

      {error && (
        <div
          className="mb-5 rounded-lg border border-danger/30 bg-danger/10 px-4 py-3 text-sm text-danger"
          role="alert"
        >
          {error}
        </div>
      )}

      <div className="space-y-4">
        {blocks.map((block, blockIndex) => (
          <Card key={block.key} padded={false}>
            <div className="flex items-center justify-between border-b border-ink-800 px-5 py-3.5">
              <div className="flex items-center gap-2.5">
                <span className="tnum flex h-6 w-6 items-center justify-center rounded-md bg-ink-800 text-xs text-ink-400">
                  {blockIndex + 1}
                </span>
                <span className="text-sm font-medium text-ink-100">
                  {block.exercise.name}
                </span>
                <Badge>{block.exercise.category}</Badge>
              </div>
              <Button
                variant="ghost"
                size="sm"
                onClick={() => removeBlock(block.key)}
                aria-label={`Remove ${block.exercise.name}`}
              >
                Remove
              </Button>
            </div>

            <div className="px-5 py-4">
              <div className="mb-2 hidden grid-cols-[2rem_1fr_1fr_1fr_auto_2rem] gap-3 text-[11px] uppercase tracking-widest text-ink-400 sm:grid">
                <span>Set</span>
                <span>Weight (kg)</span>
                <span>Reps</span>
                <span>RPE</span>
                <span>Warmup</span>
                <span />
              </div>

              <div className="space-y-2">
                {block.sets.map((set, index) => (
                  <div
                    key={index}
                    className="grid grid-cols-2 items-center gap-3 sm:grid-cols-[2rem_1fr_1fr_1fr_auto_2rem]"
                  >
                    <span className="tnum text-xs text-ink-400">{index + 1}</span>

                    <input
                      type="number"
                      inputMode="decimal"
                      step="0.5"
                      value={set.weight_kg}
                      onChange={(e) =>
                        updateSet(block.key, index, "weight_kg", e.target.value)
                      }
                      placeholder="60"
                      className="tnum rounded-lg border border-ink-700 bg-ink-850 px-3 py-2 text-sm focus:border-accent focus:outline-none"
                    />

                    <input
                      type="number"
                      inputMode="numeric"
                      value={set.reps}
                      onChange={(e) => updateSet(block.key, index, "reps", e.target.value)}
                      placeholder="5"
                      className="tnum rounded-lg border border-ink-700 bg-ink-850 px-3 py-2 text-sm focus:border-accent focus:outline-none"
                    />

                    <input
                      type="number"
                      inputMode="decimal"
                      step="0.5"
                      min="1"
                      max="10"
                      value={set.rpe}
                      onChange={(e) => updateSet(block.key, index, "rpe", e.target.value)}
                      placeholder="8"
                      className="tnum rounded-lg border border-ink-700 bg-ink-850 px-3 py-2 text-sm focus:border-accent focus:outline-none"
                    />

                    <label className="flex items-center gap-2 text-xs text-ink-400">
                      <input
                        type="checkbox"
                        checked={set.is_warmup}
                        onChange={(e) =>
                          updateSet(block.key, index, "is_warmup", e.target.checked)
                        }
                        className="h-4 w-4 rounded border-ink-600 bg-ink-850 accent-accent"
                      />
                      <span className="sm:hidden">Warmup</span>
                    </label>

                    <button
                      onClick={() => removeSet(block.key, index)}
                      disabled={block.sets.length === 1}
                      className="rounded-lg p-1.5 text-ink-400 transition-colors hover:bg-ink-800 hover:text-danger disabled:opacity-30"
                      aria-label={`Remove set ${index + 1}`}
                    >
                      <svg width="14" height="14" viewBox="0 0 24 24" fill="none">
                        <path
                          d="M5 12h14"
                          stroke="currentColor"
                          strokeWidth="2"
                          strokeLinecap="round"
                        />
                      </svg>
                    </button>
                  </div>
                ))}
              </div>

              <Button
                variant="ghost"
                size="sm"
                className="mt-3"
                onClick={() => addSet(block.key)}
              >
                + Add set
              </Button>
            </div>
          </Card>
        ))}
      </div>

      <Card className="mt-4">
        {exercises.loading ? (
          <Skeleton className="h-10 w-full" />
        ) : blocks.length === 0 ? (
          <EmptyState
            title="Nothing added yet"
            description="Pick your first exercise to start the session."
            action={
              <div className="w-64">
                <Select value={picker} onChange={(e) => addExercise(e.target.value)}>
                  <option value="">Choose an exercise…</option>
                  {exercises.data?.map((exercise) => (
                    <option key={exercise.id} value={exercise.id}>
                      {exercise.name}
                    </option>
                  ))}
                </Select>
              </div>
            }
          />
        ) : (
          <div className="sm:max-w-xs">
            <Select
              label="Add another exercise"
              value={picker}
              onChange={(e) => addExercise(e.target.value)}
            >
              <option value="">Choose an exercise…</option>
              {exercises.data?.map((exercise) => (
                <option key={exercise.id} value={exercise.id}>
                  {exercise.name}
                </option>
              ))}
            </Select>
          </div>
        )}
      </Card>

      {workingSets > 0 && (
        <div className="mt-5 flex items-center justify-between rounded-xl border border-ink-800 bg-ink-900 px-5 py-4">
          <div className="text-sm text-ink-400">
            <span className="tnum font-medium text-ink-100">{workingSets}</span> working
            sets ·{" "}
            <span className="tnum font-medium text-accent">{volume(totalVolume)} kg</span>{" "}
            total
          </div>
          <Button size="lg" onClick={save} loading={saving}>
            Save workout
          </Button>
        </div>
      )}
    </div>
  );
}
