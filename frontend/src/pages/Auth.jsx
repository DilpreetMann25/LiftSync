/** Sign in and registration, on one screen with a mode toggle. */

import { useState } from "react";
import { useAuth } from "../context/AuthContext";
import { Button, Input } from "../components/ui";

const DEMO = { email: "demo@liftsync.app", password: "liftsync-demo-2026" };

export default function Auth() {
  const { login, register } = useAuth();
  const [mode, setMode] = useState("login");
  const [form, setForm] = useState({
    email: "",
    password: "",
    display_name: "",
    height_cm: "",
  });
  const [error, setError] = useState(null);
  const [busy, setBusy] = useState(false);

  const set = (key) => (event) =>
    setForm((prev) => ({ ...prev, [key]: event.target.value }));

  async function submit(event) {
    event.preventDefault();
    setError(null);
    setBusy(true);

    try {
      if (mode === "login") {
        await login(form.email, form.password);
      } else {
        await register({
          email: form.email,
          password: form.password,
          display_name: form.display_name,
          // The API expects a number or null, never an empty string.
          height_cm: form.height_cm ? Number(form.height_cm) : null,
        });
      }
    } catch (err) {
      setError(err.message);
    } finally {
      // In finally, so the button is re-enabled even when the request
      // throws. Forgetting this leaves a permanently spinning form.
      setBusy(false);
    }
  }

  async function loginAsDemo() {
    setError(null);
    setBusy(true);
    try {
      await login(DEMO.email, DEMO.password);
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="flex min-h-screen">
      {/* Left: the pitch. Hidden on mobile, where it would just push
          the form below the fold. */}
      <div className="relative hidden w-1/2 flex-col justify-between overflow-hidden border-r border-ink-800 bg-ink-900 p-12 lg:flex">
        <div
          className="pointer-events-none absolute inset-0 opacity-[0.06]"
          style={{
            backgroundImage:
              "linear-gradient(var(--color-ink-100) 1px, transparent 1px), linear-gradient(90deg, var(--color-ink-100) 1px, transparent 1px)",
            backgroundSize: "44px 44px",
          }}
          aria-hidden="true"
        />

        <div className="relative flex items-center gap-2.5">
          <div className="flex h-8 w-8 items-center justify-center rounded-md bg-accent text-sm font-bold text-ink-950">
            L
          </div>
          <span className="font-semibold tracking-tight">LiftSync</span>
        </div>

        <div className="relative max-w-md">
          <h1 className="text-3xl font-semibold leading-tight tracking-tight">
            Your training data,
            <br />
            <span className="text-accent">read properly.</span>
          </h1>
          <p className="mt-4 text-sm leading-relaxed text-ink-400">
            Track compound lifts, map progressive overload, and let an AI coach
            that actually queries your history diagnose the plateau — and
            programme around it.
          </p>

          <div className="mt-8 space-y-3">
            {[
              "Estimated 1RM and rolling trend per lift",
              "Plateau detection tuned per exercise type",
              "Macro intake correlated with strength output",
            ].map((line) => (
              <div key={line} className="flex items-start gap-2.5 text-sm text-ink-300">
                <span className="mt-1.5 h-1 w-1 shrink-0 rounded-full bg-accent" />
                {line}
              </div>
            ))}
          </div>
        </div>

        <div className="relative text-xs text-ink-400">
          PostgreSQL · FastAPI · React · Gemini
        </div>
      </div>

      {/* Right: the form. */}
      <div className="flex w-full items-center justify-center px-6 py-12 lg:w-1/2">
        <div className="w-full max-w-sm animate-fade-up">
          <div className="mb-8">
            <h2 className="text-lg font-semibold tracking-tight">
              {mode === "login" ? "Sign in" : "Create your account"}
            </h2>
            <p className="mt-1 text-sm text-ink-400">
              {mode === "login"
                ? "Pick up where you left off."
                : "Start tracking in under a minute."}
            </p>
          </div>

          <form onSubmit={submit} className="space-y-4">
            {mode === "register" && (
              <Input
                label="Name"
                value={form.display_name}
                onChange={set("display_name")}
                placeholder="Dilpreet"
                required
              />
            )}

            <Input
              label="Email"
              type="email"
              value={form.email}
              onChange={set("email")}
              placeholder="you@example.com"
              autoComplete="email"
              required
            />

            <Input
              label="Password"
              type="password"
              value={form.password}
              onChange={set("password")}
              placeholder="At least 8 characters"
              // Tells password managers whether to offer a saved
              // password or suggest a new one.
              autoComplete={mode === "login" ? "current-password" : "new-password"}
              minLength={8}
              required
            />

            {mode === "register" && (
              <Input
                label="Height (cm)"
                type="number"
                value={form.height_cm}
                onChange={set("height_cm")}
                placeholder="178"
                hint="Optional"
              />
            )}

            {error && (
              <div
                className="rounded-lg border border-danger/30 bg-danger/10 px-3 py-2 text-xs text-danger"
                role="alert"
              >
                {error}
              </div>
            )}

            <Button type="submit" size="lg" className="w-full" loading={busy}>
              {mode === "login" ? "Sign in" : "Create account"}
            </Button>
          </form>

          <div className="my-6 flex items-center gap-3">
            <div className="h-px flex-1 bg-ink-800" />
            <span className="text-[11px] uppercase tracking-widest text-ink-400">or</span>
            <div className="h-px flex-1 bg-ink-800" />
          </div>

          {/* Anyone evaluating this repo can be looking at real data in
              one click, instead of registering and finding it empty. */}
          <Button
            variant="secondary"
            size="lg"
            className="w-full"
            onClick={loginAsDemo}
            disabled={busy}
          >
            Explore the demo account
          </Button>
          <p className="mt-2 text-center text-[11px] text-ink-400">
            8 weeks of seeded training data, plateau included
          </p>

          <p className="mt-8 text-center text-xs text-ink-400">
            {mode === "login" ? "No account yet?" : "Already registered?"}{" "}
            <button
              onClick={() => {
                setMode(mode === "login" ? "register" : "login");
                setError(null);
              }}
              className="font-medium text-accent hover:underline"
            >
              {mode === "login" ? "Create one" : "Sign in"}
            </button>
          </p>
        </div>
      </div>
    </div>
  );
}
