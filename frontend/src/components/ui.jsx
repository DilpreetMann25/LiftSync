/**
 * Shared UI primitives.
 *
 * Every card, button, and badge in the app comes from here. The point
 * is not to save typing -- it is that a restyle happens in one file,
 * and nothing can drift into being subtly the wrong grey.
 */

export function Card({ children, className = "", padded = true, ...rest }) {
  return (
    <div
      className={`rounded-xl border border-ink-800 bg-ink-900 ${
        padded ? "p-5" : ""
      } ${className}`}
      {...rest}
    >
      {children}
    </div>
  );
}

export function CardHeader({ title, subtitle, action }) {
  return (
    <div className="mb-4 flex items-start justify-between gap-4">
      <div>
        <h2 className="text-sm font-semibold tracking-wide text-ink-100">{title}</h2>
        {subtitle && <p className="mt-0.5 text-xs text-ink-400">{subtitle}</p>}
      </div>
      {action}
    </div>
  );
}

export function Stat({ label, value, unit, delta, tone = "default" }) {
  const tones = {
    default: "text-ink-100",
    accent: "text-accent",
    warn: "text-warn",
    danger: "text-danger",
  };

  return (
    <div>
      <div className="text-[11px] font-medium uppercase tracking-widest text-ink-400">
        {label}
      </div>
      <div className="mt-1.5 flex items-baseline gap-1.5">
        {/* tnum keeps digits the same width so numbers do not jitter. */}
        <span className={`tnum text-2xl font-semibold ${tones[tone]}`}>{value}</span>
        {unit && <span className="text-xs text-ink-400">{unit}</span>}
      </div>
      {delta && <div className="mt-1 text-xs text-ink-400">{delta}</div>}
    </div>
  );
}

export function Badge({ children, tone = "neutral", className = "" }) {
  const tones = {
    neutral: "border-ink-700 bg-ink-800 text-ink-300",
    accent: "border-accent/30 bg-accent/10 text-accent",
    warn: "border-warn/30 bg-warn/10 text-warn",
    danger: "border-danger/30 bg-danger/10 text-danger",
    info: "border-info/30 bg-info/10 text-info",
  };

  return (
    <span
      className={`inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-[11px] font-medium ${tones[tone]} ${className}`}
    >
      {children}
    </span>
  );
}

export function Button({
  children,
  variant = "primary",
  size = "md",
  className = "",
  loading = false,
  ...rest
}) {
  const variants = {
    primary: "bg-accent text-ink-950 hover:bg-accent-dim disabled:bg-accent/40",
    secondary:
      "border border-ink-700 bg-ink-800 text-ink-100 hover:border-ink-600 hover:bg-ink-700",
    ghost: "text-ink-300 hover:bg-ink-800 hover:text-ink-100",
    danger: "border border-danger/30 bg-danger/10 text-danger hover:bg-danger/20",
  };

  const sizes = {
    sm: "px-2.5 py-1 text-xs",
    md: "px-3.5 py-2 text-sm",
    lg: "px-5 py-2.5 text-sm",
  };

  return (
    <button
      className={`inline-flex items-center justify-center gap-2 rounded-lg font-medium transition-colors disabled:cursor-not-allowed disabled:opacity-60 ${variants[variant]} ${sizes[size]} ${className}`}
      disabled={loading || rest.disabled}
      {...rest}
    >
      {loading && <Spinner size={14} />}
      {children}
    </button>
  );
}

export function Input({ label, hint, error, className = "", ...rest }) {
  return (
    <label className="block">
      {label && (
        <span className="mb-1.5 block text-xs font-medium text-ink-300">{label}</span>
      )}
      <input
        className={`w-full rounded-lg border bg-ink-850 px-3 py-2 text-sm text-ink-100 placeholder-ink-400 transition-colors focus:border-accent focus:outline-none ${
          error ? "border-danger" : "border-ink-700"
        } ${className}`}
        {...rest}
      />
      {error && <span className="mt-1 block text-xs text-danger">{error}</span>}
      {hint && !error && <span className="mt-1 block text-xs text-ink-400">{hint}</span>}
    </label>
  );
}

export function Select({ label, children, className = "", ...rest }) {
  return (
    <label className="block">
      {label && (
        <span className="mb-1.5 block text-xs font-medium text-ink-300">{label}</span>
      )}
      <select
        className={`w-full rounded-lg border border-ink-700 bg-ink-850 px-3 py-2 text-sm text-ink-100 focus:border-accent focus:outline-none ${className}`}
        {...rest}
      >
        {children}
      </select>
    </label>
  );
}

export function Spinner({ size = 16, className = "" }) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      className={`animate-spin ${className}`}
      aria-hidden="true"
    >
      <circle cx="12" cy="12" r="9" stroke="currentColor" strokeWidth="3" opacity="0.2" />
      <path
        d="M21 12a9 9 0 0 0-9-9"
        stroke="currentColor"
        strokeWidth="3"
        strokeLinecap="round"
      />
    </svg>
  );
}

/**
 * Skeletons rather than a spinner for page-level loading.
 *
 * A block roughly the shape of the incoming content stops the layout
 * jumping when data lands, and makes the wait feel shorter than a
 * spinner in an empty space does.
 */
export function Skeleton({ className = "" }) {
  return <div className={`animate-pulse rounded-lg bg-ink-800 ${className}`} />;
}

export function EmptyState({ icon, title, description, action }) {
  return (
    <div className="flex flex-col items-center justify-center px-6 py-14 text-center">
      {icon && <div className="mb-3 text-ink-600">{icon}</div>}
      <h3 className="text-sm font-medium text-ink-200">{title}</h3>
      {description && (
        <p className="mt-1.5 max-w-sm text-xs leading-relaxed text-ink-400">
          {description}
        </p>
      )}
      {action && <div className="mt-4">{action}</div>}
    </div>
  );
}

export function ErrorState({ error, onRetry }) {
  return (
    <div className="flex flex-col items-center justify-center px-6 py-12 text-center">
      <div className="mb-2 text-danger">
        <svg width="24" height="24" viewBox="0 0 24 24" fill="none" aria-hidden="true">
          <path
            d="M12 9v4m0 4h.01M10.3 3.9 1.8 18a2 2 0 0 0 1.7 3h17a2 2 0 0 0 1.7-3L13.7 3.9a2 2 0 0 0-3.4 0Z"
            stroke="currentColor"
            strokeWidth="1.8"
            strokeLinecap="round"
            strokeLinejoin="round"
          />
        </svg>
      </div>
      <h3 className="text-sm font-medium text-ink-200">Something went wrong</h3>
      <p className="mt-1.5 max-w-sm text-xs text-ink-400">
        {error?.message || "Unknown error"}
      </p>
      {onRetry && (
        <Button variant="secondary" size="sm" className="mt-4" onClick={onRetry}>
          Try again
        </Button>
      )}
    </div>
  );
}

export function PageHeader({ title, description, action }) {
  return (
    <div className="mb-6 flex flex-wrap items-end justify-between gap-4">
      <div>
        <h1 className="text-xl font-semibold tracking-tight text-ink-100">{title}</h1>
        {description && <p className="mt-1 text-sm text-ink-400">{description}</p>}
      </div>
      {action}
    </div>
  );
}
