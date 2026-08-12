/** Small formatting helpers, kept together so output stays consistent. */

export function kg(value, decimals = 1) {
  if (value === null || value === undefined) return "—";
  return `${Number(value).toFixed(decimals)} kg`;
}

/** Volume runs to five digits, so 12400 reads better as 12.4k. */
export function volume(value) {
  if (value === null || value === undefined) return "—";
  const n = Number(value);
  if (n >= 10000) return `${(n / 1000).toFixed(1)}k`;
  return n.toFixed(0);
}

export function shortDate(iso) {
  if (!iso) return "—";
  return new Date(`${iso}T00:00:00`).toLocaleDateString(undefined, {
    day: "numeric",
    month: "short",
  });
}

export function fullDate(iso) {
  if (!iso) return "—";
  return new Date(`${iso}T00:00:00`).toLocaleDateString(undefined, {
    weekday: "short",
    day: "numeric",
    month: "short",
    year: "numeric",
  });
}

export function relativeDays(iso) {
  if (!iso) return "—";
  const days = Math.round(
    (Date.now() - new Date(`${iso}T00:00:00`).getTime()) / 86400000
  );
  if (days === 0) return "today";
  if (days === 1) return "yesterday";
  if (days < 7) return `${days} days ago`;
  if (days < 14) return "last week";
  return `${Math.floor(days / 7)} weeks ago`;
}

/** Signed, so a change of +2.5 reads unambiguously. */
export function delta(value, suffix = "") {
  if (value === null || value === undefined) return null;
  const n = Number(value);
  const sign = n > 0 ? "+" : "";
  return `${sign}${n.toFixed(1)}${suffix}`;
}

/** front_delts -> Front Delts */
export function muscleLabel(name) {
  return name
    .split("_")
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
    .join(" ");
}
