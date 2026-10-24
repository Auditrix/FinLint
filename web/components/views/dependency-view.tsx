"use client";

import { motion } from "framer-motion";
import { AlertCircle, ArrowRight, Loader2, Search } from "lucide-react";
import * as React from "react";

import { SeverityPill } from "@/components/ui/pill";
import * as api from "@/lib/api";
import { ruleInfo } from "@/lib/rules";
import type { CellInspect } from "@/lib/types";
import { cellRef, cn, formatInt, formatValue, splitRef } from "@/lib/utils";

import { useWorkspace } from "../workspace-context";
import { PageHeader } from "./page-header";

const SHOWN = 12;

export function DependencyView() {
  const { run, selected, select, setView } = useWorkspace();
  const [query, setQuery] = React.useState("");
  const [cell, setCell] = React.useState<CellInspect | null>(null);
  const [error, setError] = React.useState<string | null>(null);
  const [loading, setLoading] = React.useState(false);

  // Ranked by how much each finding breaks downstream.
  const leaders = React.useMemo(
    () => (run ? [...run.findings].sort((a, b) => b.blast_radius - a.blast_radius).slice(0, 8) : []),
    [run],
  );
  const fallback = leaders[0] ? cellRef(leaders[0].sheet, leaders[0].coordinate) : null;
  const focus = selected ?? fallback;

  React.useEffect(() => {
    if (!run || !focus) return;
    let cancelled = false;
    // Cleared first, so the previous cell's graph never sits beside the new
    // cell's finding while the new one loads.
    setCell(null);
    setLoading(true);
    setError(null);
    api
      .getCell(run.file, focus)
      .then((c) => !cancelled && setCell(c))
      .catch((e) => !cancelled && setError(e instanceof Error ? e.message : "Could not load this cell."))
      .finally(() => !cancelled && setLoading(false));
    return () => {
      cancelled = true;
    };
  }, [run, focus]);

  if (!run) return null;
  const finding = focus ? run.findings.find((f) => cellRef(f.sheet, f.coordinate) === focus) : undefined;

  function go(e: React.FormEvent) {
    e.preventDefault();
    const q = query.trim();
    if (!q) return;
    // Accept "Sheet!A1", or a bare cell on the sheet already in view.
    select(q.includes("!") ? q : cell ? cellRef(cell.sheet, q.toUpperCase()) : q);
  }

  return (
    <div className="scroll-thin h-full overflow-y-auto">
      <div className="space-y-4 p-5">
        <PageHeader
          title="Dependency map"
          description={`What each cell reads and what reads it, across ${formatInt(run.stats.formulas)} formulas and ${formatInt(run.stats.links)} links. The downstream count is how far one wrong number travels.`}
          actions={
            <form onSubmit={go} className="flex h-8 items-center gap-2 rounded-md border border-hairline bg-surface px-2.5">
              <Search className="h-3.5 w-3.5 text-ink-muted" strokeWidth={1.5} />
              <input
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                placeholder="Sheet!A1"
                className="w-40 bg-transparent font-mono text-xs text-ink outline-none placeholder:text-ink-muted"
              />
            </form>
          }
        />

        <div className="grid grid-cols-1 gap-4 xl:grid-cols-[1fr_20rem]">
          <section className="panel p-5">
            {loading && !cell && (
              <div className="flex items-center gap-2 py-16 text-xs text-ink-muted">
                <Loader2 className="h-3.5 w-3.5 animate-spin text-accent" strokeWidth={1.5} />
                Tracing
              </div>
            )}
            {error && (
              <div className="flex items-start gap-2 rounded-md border border-hairline bg-canvas px-3 py-2.5 text-xs text-ink-secondary">
                <AlertCircle className="mt-0.5 h-3.5 w-3.5 shrink-0 text-ink-muted" strokeWidth={1.5} />
                {error}
              </div>
            )}
            {cell && !error && <Graph cell={cell} onOpen={select} />}
            {cell && finding && !error && (
              <div className="mt-5 flex flex-wrap items-center justify-between gap-3 border-t border-hairline pt-4">
                <div className="flex items-center gap-2 text-[13px]">
                  <SeverityPill severity={finding.severity} />
                  <span className="font-medium text-ink">{ruleInfo(finding.rule_id).label}</span>
                  <span className="text-ink-muted">on this cell</span>
                </div>
                <button
                  onClick={() => {
                    // Both are needed. With no cell in the URL the map shows the
                    // largest blast radius, but the findings view would open on
                    // its own first row, a different finding.
                    setView("findings");
                    if (focus) select(focus);
                  }}
                  className="inline-flex items-center gap-1 text-xs font-medium text-accent hover:underline"
                >
                  Open in findings
                  <ArrowRight className="h-3 w-3" strokeWidth={1.5} />
                </button>
              </div>
            )}
          </section>

          <section className="panel overflow-hidden">
            <div className="border-b border-hairline px-4 py-3">
              <div className="eyebrow">Largest blast radius</div>
              <p className="mt-1 text-xs text-ink-muted">The findings whose mistake would spread furthest.</p>
            </div>
            <ul className="divide-y divide-hairline">
              {leaders.map((f) => {
                const ref = cellRef(f.sheet, f.coordinate);
                const top = leaders[0]?.blast_radius || 1;
                return (
                  <li key={`${f.rule_id}|${ref}`}>
                    <button
                      onClick={() => select(ref)}
                      className={cn(
                        "w-full px-4 py-2.5 text-left transition-colors",
                        ref === focus ? "bg-indigo-50/40" : "hover:bg-slate-50/80",
                      )}
                    >
                      <div className="flex items-center justify-between gap-2">
                        <span className="truncate font-mono text-xs text-ink">{ref}</span>
                        <span className="font-mono text-xs tabular-nums text-trace">{formatInt(f.blast_radius)}</span>
                      </div>
                      <div className="mt-1.5 h-1 overflow-hidden rounded-full bg-recessed">
                        <div className="h-full rounded-full bg-trace" style={{ width: `${(f.blast_radius / top) * 100}%` }} />
                      </div>
                      <div className="mt-1 truncate text-2xs text-ink-muted">{ruleInfo(f.rule_id).label}</div>
                    </button>
                  </li>
                );
              })}
            </ul>
          </section>
        </div>
      </div>
    </div>
  );
}

/**
 * Three columns: what this cell reads, the cell, what reads it. The connectors
 * are drawn from measured geometry, not guessed percentages, so every curve
 * starts at its own chip and lands on the cell card at any width.
 */
// Full size on a desktop, compact when the panel is narrow, so the three
// columns never overlap. Both are derived from the measured width.
const ROOMY = { card: 224, gap: 56 };
const COMPACT = { card: 150, gap: 20 };
const COMPACT_BELOW = 520;

function Graph({ cell, onOpen }: { cell: CellInspect; onOpen: (ref: string) => void }) {
  const left = cell.precedents.slice(0, SHOWN);
  const right = cell.dependents.slice(0, SHOWN);
  const rows = Math.max(left.length, right.length, 1);
  const height = Math.max(rows * 30, 140);

  const box = React.useRef<HTMLDivElement>(null);
  const [width, setWidth] = React.useState(0);

  // Measured before the browser paints, then kept current. A resize observer
  // alone does not reliably report the first size, which left the connectors
  // undrawn on whichever cell the view happened to open on.
  React.useLayoutEffect(() => {
    const el = box.current;
    if (!el) return;
    setWidth(el.getBoundingClientRect().width);
    const observer = new ResizeObserver(([entry]) => entry && setWidth(entry.contentRect.width));
    observer.observe(el);
    return () => observer.disconnect();
  }, []);

  const { card: CARD, gap: GAP } = width > 0 && width < COMPACT_BELOW ? COMPACT : ROOMY;

  // Chip slots are spread evenly down each column, the same way justify-around
  // spaces the chips themselves.
  const slot = (i: number, n: number) => (height / n) * (i + 0.5);
  const side = Math.max(0, (width - CARD - GAP * 2) / 2);
  const mid = height / 2;

  return (
    <div>
      <div
        className="mb-3 grid text-center"
        style={{ gridTemplateColumns: `minmax(0,1fr) ${CARD}px minmax(0,1fr)`, columnGap: GAP }}
      >
        <div className="eyebrow">Reads · {formatInt(cell.precedents_total)}</div>
        <div className="eyebrow">Cell</div>
        <div className="eyebrow">Read by · {formatInt(cell.dependents_total)}</div>
      </div>

      <div
        ref={box}
        className="relative grid"
        style={{ height, gridTemplateColumns: `minmax(0,1fr) ${CARD}px minmax(0,1fr)`, columnGap: GAP }}
      >
        {width > 0 && (
          <svg className="pointer-events-none absolute inset-0" width={width} height={height} aria-hidden>
            {left.map((_, i) => (
              <Connector key={`l${i}`} x1={side} y1={slot(i, left.length)} x2={side + GAP} y2={mid} />
            ))}
            {right.map((_, i) => (
              <Connector
                key={`r${i}`}
                x1={side + GAP + CARD}
                y1={mid}
                x2={side + GAP * 2 + CARD}
                y2={slot(i, right.length)}
              />
            ))}
          </svg>
        )}

        <Column refs={left} home={cell.sheet} total={cell.precedents_total} height={height} align="end" onOpen={onOpen} />

        <motion.div
          key={cell.ref}
          initial={{ opacity: 0, scale: 0.98 }}
          animate={{ opacity: 1, scale: 1 }}
          transition={{ type: "spring", stiffness: 400, damping: 30 }}
          className="relative z-10 flex flex-col justify-center self-center rounded-lg border border-accent bg-surface p-3 shadow-hairline"
        >
          <div className="truncate font-mono text-[13px] font-medium text-ink">{cell.ref}</div>
          <div className="code-surface mt-2 truncate px-2 py-1.5">{cell.formula ?? formatValue(cell.value)}</div>
          <div className="mt-2 flex items-baseline justify-between text-2xs">
            <span className="text-ink-muted">downstream</span>
            <span className="font-mono text-[13px] font-medium tabular-nums text-trace">{formatInt(cell.blast_radius)}</span>
          </div>
        </motion.div>

        <Column refs={right} home={cell.sheet} total={cell.dependents_total} height={height} align="start" onOpen={onOpen} />
      </div>

      {cell.precedents_total === 0 && cell.dependents_total === 0 && (
        <p className="mt-4 text-center text-xs text-ink-muted">This cell neither reads nor is read by any formula.</p>
      )}
    </div>
  );
}

function Column({
  refs,
  home,
  total,
  height,
  align,
  onOpen,
}: {
  refs: string[];
  home: string;
  total: number;
  height: number;
  align: "start" | "end";
  onOpen: (ref: string) => void;
}) {
  return (
    <div className={cn("relative z-10 flex min-w-0 flex-col justify-around", align === "end" ? "items-end" : "items-start")} style={{ height }}>
      {refs.length === 0 ? (
        <span className="self-center text-2xs text-ink-muted">none</span>
      ) : (
        refs.map((ref) => {
          const { sheet, coordinate } = splitRef(ref);
          return (
            <button
              key={ref}
              onClick={() => onOpen(ref)}
              title={ref}
              className="max-w-full truncate rounded border border-sky-200 bg-sky-50 px-2 py-0.5 font-mono text-2xs text-sky-700 transition-colors hover:border-sky-300 hover:bg-sky-100"
            >
              {sheet === home ? coordinate : ref}
            </button>
          );
        })
      )}
      {total > refs.length && (
        <span className={cn("absolute -bottom-5 font-mono text-2xs text-ink-muted", align === "end" ? "right-0" : "left-0")}>
          +{formatInt(total - refs.length)} more
        </span>
      )}
    </div>
  );
}

function Connector({ x1, y1, x2, y2 }: { x1: number; y1: number; x2: number; y2: number }) {
  const bend = (x2 - x1) / 2;
  return (
    <path
      d={`M${x1},${y1} C${x1 + bend},${y1} ${x2 - bend},${y2} ${x2},${y2}`}
      fill="none"
      stroke="#BAE6FD"
      strokeWidth="1"
    />
  );
}
