/**
 * Chart building blocks.
 *
 * Recharts defaults are built for light backgrounds, so every chart
 * needs the same set of overrides. Doing that once here keeps the
 * pages readable and the charts consistent.
 */

import {
  Area,
  AreaChart,
  Bar,
  BarChart,
  CartesianGrid,
  Line,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

const AXIS = {
  stroke: "#6b7480",
  fontSize: 11,
  tickLine: false,
  axisLine: false,
};

/** 15000 -> "15k", 2500 -> "2.5k", 800 -> "800". For axis ticks only. */
function compactNumber(value) {
  if (Math.abs(value) < 1000) return String(value);
  const thousands = value / 1000;
  return `${Number.isInteger(thousands) ? thousands : thousands.toFixed(1)}k`;
}

/** A tooltip that matches the app rather than Recharts' white default. */
function DarkTooltip({ active, payload, label, formatter }) {
  if (!active || !payload?.length) return null;

  return (
    <div className="rounded-lg border border-ink-700 bg-ink-850 px-3 py-2 shadow-xl">
      <div className="mb-1 text-[11px] font-medium text-ink-300">{label}</div>
      {payload.map((entry) => (
        <div key={entry.dataKey} className="flex items-center gap-2 text-xs">
          <span
            className="h-2 w-2 rounded-full"
            style={{ background: entry.color }}
            aria-hidden="true"
          />
          <span className="text-ink-400">{entry.name}</span>
          <span className="tnum ml-auto font-medium text-ink-100">
            {formatter ? formatter(entry.value) : entry.value}
          </span>
        </div>
      ))}
    </div>
  );
}

export function ProgressionChart({ data, height = 260 }) {
  return (
    <ResponsiveContainer width="100%" height={height}>
      <AreaChart data={data} margin={{ top: 8, right: 8, left: -18, bottom: 0 }}>
        <defs>
          <linearGradient id="e1rmFill" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor="#4ade80" stopOpacity={0.28} />
            <stop offset="100%" stopColor="#4ade80" stopOpacity={0} />
          </linearGradient>
        </defs>

        <CartesianGrid stroke="#232830" vertical={false} />
        <XAxis dataKey="label" {...AXIS} />
        {/* domain 'auto' rather than starting at zero: strength moves
            in small increments, and a zero baseline would flatten a
            real 10% gain into a visually straight line. */}
        <YAxis {...AXIS} domain={["auto", "auto"]} width={44} />
        <Tooltip content={<DarkTooltip formatter={(v) => `${v} kg`} />} />

        <Area
          type="monotone"
          dataKey="e1rm"
          name="e1RM"
          stroke="#4ade80"
          strokeWidth={2}
          fill="url(#e1rmFill)"
          dot={{ r: 2.5, fill: "#4ade80", strokeWidth: 0 }}
          activeDot={{ r: 4 }}
        />
        {/* The rolling average is the signal; the raw line is the
            noise around it. Dashed so the eye reads it as secondary. */}
        <Line
          type="monotone"
          dataKey="rolling_e1rm"
          name="3-session avg"
          stroke="#60a5fa"
          strokeWidth={1.5}
          strokeDasharray="4 4"
          dot={false}
        />
      </AreaChart>
    </ResponsiveContainer>
  );
}

export function VolumeBarChart({ data, height = 240, formatter }) {
  return (
    <ResponsiveContainer width="100%" height={height}>
      <BarChart data={data} margin={{ top: 8, right: 8, left: -18, bottom: 0 }}>
        <CartesianGrid stroke="#232830" vertical={false} />
        <XAxis dataKey="label" {...AXIS} />
        {/* Weekly volume runs to five digits, which overflows a narrow
            axis and gets clipped. 15000 -> 15k keeps every label short;
            the tooltip still shows the exact figure. */}
        <YAxis {...AXIS} width={44} tickFormatter={compactNumber} />
        <Tooltip
          content={<DarkTooltip formatter={formatter} />}
          cursor={{ fill: "#171b21" }}
        />
        <Bar dataKey="value" name="Volume" fill="#4ade80" radius={[3, 3, 0, 0]} />
      </BarChart>
    </ResponsiveContainer>
  );
}

/**
 * A tiny inline chart with no axes, for use inside a card.
 * Shows shape only -- direction and volatility, not values.
 */
export function Sparkline({ data, width = 96, height = 28, color = "#4ade80" }) {
  if (!data || data.length < 2) return null;

  const values = data.map((d) => Number(d));
  const min = Math.min(...values);
  const max = Math.max(...values);
  // Guard against a flat series: max - min would be 0 and every point
  // would divide by zero.
  const range = max - min || 1;

  const points = values
    .map((value, index) => {
      const x = (index / (values.length - 1)) * width;
      const y = height - ((value - min) / range) * height;
      return `${x.toFixed(1)},${y.toFixed(1)}`;
    })
    .join(" ");

  return (
    <svg width={width} height={height} className="overflow-visible" aria-hidden="true">
      <polyline
        points={points}
        fill="none"
        stroke={color}
        strokeWidth="1.5"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  );
}
