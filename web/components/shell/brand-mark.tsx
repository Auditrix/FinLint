/**
 * A three by three grid of cells with one picked out: FinLint's whole job is
 * pointing at the exact cell. Drawn in SVG so it stays crisp at any size.
 */
export function BrandMark({ className }: { className?: string }) {
  return (
    <svg viewBox="0 0 20 20" className={className} aria-hidden>
      <rect x="0.5" y="0.5" width="19" height="19" rx="4.5" fill="#0F172A" />
      {[0, 1, 2].map((r) =>
        [0, 1, 2].map((c) => {
          const picked = r === 1 && c === 2;
          return (
            <rect
              key={`${r}-${c}`}
              x={4 + c * 4.25}
              y={4 + r * 4.25}
              width="3.25"
              height="3.25"
              rx="0.7"
              fill={picked ? "#818CF8" : "#334155"}
            />
          );
        }),
      )}
    </svg>
  );
}
