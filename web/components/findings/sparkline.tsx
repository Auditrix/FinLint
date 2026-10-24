import * as React from "react";

/**
 * A single stroke line with a faint fill, drawn to the data's own scale. With
 * one point there is nothing to trend, so it says so instead of drawing a dot
 * that pretends to be a chart.
 */
export function Sparkline({
  values,
  stroke = "#4F46E5",
  max,
  min = 0,
  className,
}: {
  values: number[];
  stroke?: string;
  max?: number;
  min?: number;
  className?: string;
}) {
  const id = React.useId().replace(/:/g, "");
  const width = 120;
  const height = 32;
  const pad = 2;

  if (values.length < 2) {
    return <span className="font-mono text-2xs text-ink-muted">one version, no trend yet</span>;
  }

  const top = max ?? Math.max(...values);
  const span = top - min || 1;
  const step = (width - pad * 2) / (values.length - 1);
  const points = values.map((v, i) => {
    const x = pad + i * step;
    const y = pad + (height - pad * 2) * (1 - (v - min) / span);
    return [x, y] as const;
  });
  const line = points.map(([x, y], i) => `${i === 0 ? "M" : "L"}${x.toFixed(1)},${y.toFixed(1)}`).join(" ");
  const area = `${line} L${points[points.length - 1]![0].toFixed(1)},${height - pad} L${pad},${height - pad} Z`;
  const last = points[points.length - 1]!;

  return (
    <svg viewBox={`0 0 ${width} ${height}`} className={className} preserveAspectRatio="none" aria-hidden>
      <defs>
        <linearGradient id={id} x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor={stroke} stopOpacity="0.16" />
          <stop offset="100%" stopColor={stroke} stopOpacity="0" />
        </linearGradient>
      </defs>
      <path d={area} fill={`url(#${id})`} />
      <path d={line} fill="none" stroke={stroke} strokeWidth="1.5" strokeLinejoin="round" strokeLinecap="round" />
      <circle cx={last[0]} cy={last[1]} r="2.25" fill={stroke} />
    </svg>
  );
}
