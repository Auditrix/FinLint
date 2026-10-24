"use client";

import { AnimatePresence, motion } from "framer-motion";
import { AlertCircle, ArrowLeft, Check, Copy, Loader2, MousePointerClick } from "lucide-react";
import * as React from "react";

import { SeverityPill, Tag } from "@/components/ui/pill";
import { Tip } from "@/components/ui/tooltip";
import * as api from "@/lib/api";
import { ruleInfo } from "@/lib/rules";
import type { AnnotatedFinding, CellInspect, RunDetail } from "@/lib/types";
import { cellRef, cn, formatValue } from "@/lib/utils";

import { useWorkspace } from "../workspace-context";
import { Decision } from "./decision";
import { Evidence } from "./evidence";
import { RowCompare } from "./row-compare";
import { Trace } from "./trace";

const cache = new Map<string, Promise<CellInspect>>();

// Keyed by run as well as cell. Checking a new version of the same workbook
// must not show a formula's old text from the previous version.
function loadCell(file: string, runId: number, ref: string): Promise<CellInspect> {
  const key = `${file}|${runId}|${ref}`;
  let hit = cache.get(key);
  if (!hit) {
    hit = api.getCell(file, ref);
    cache.set(key, hit);
    hit.catch(() => cache.delete(key)); // a failure should be retryable
  }
  return hit;
}

export function Inspector({ run, cellRefSelected }: { run: RunDetail; cellRefSelected: string | null }) {
  const { select } = useWorkspace();
  const [cell, setCell] = React.useState<CellInspect | null>(null);
  const [error, setError] = React.useState<string | null>(null);
  const [loading, setLoading] = React.useState(false);
  const [trail, setTrail] = React.useState<string[]>([]);

  const ref = cellRefSelected;
  const finding: AnnotatedFinding | undefined = ref
    ? run.findings.find((f) => cellRef(f.sheet, f.coordinate) === ref)
    : undefined;

  React.useEffect(() => {
    if (!ref) return;
    let cancelled = false;
    // Cleared first. Keeping the old cell made the loading guard false, so the
    // panel went blank instead of showing the spinner.
    setCell(null);
    setLoading(true);
    setError(null);
    loadCell(run.file, run.run_id, ref)
      .then((c) => !cancelled && setCell(c))
      .catch((e) => {
        if (cancelled) return;
        setCell(null);
        setError(e instanceof Error ? e.message : "Could not load this cell.");
      })
      .finally(() => !cancelled && setLoading(false));
    return () => {
      cancelled = true;
    };
  }, [run.file, run.run_id, ref]);

  // "Back" belongs to one walk through the trace. A selection made anywhere
  // else, a row in the table, the palette, another file, starts a new walk;
  // otherwise Back could select a cell from a different workbook.
  const walking = React.useRef(false);

  React.useEffect(() => {
    if (walking.current) {
      walking.current = false;
      return;
    }
    setTrail([]);
  }, [ref, run.file]);

  function openCell(next: string) {
    // A cell that refers to itself lists itself as a chip. Selecting it would
    // not change the selection, so the flag below would never be cleared.
    if (next === ref) return;
    if (ref) setTrail((t) => [...t, ref]);
    walking.current = true;
    select(next);
  }

  function back() {
    const previous = trail[trail.length - 1];
    if (!previous) return;
    setTrail((t) => t.slice(0, -1));
    walking.current = true;
    select(previous);
  }

  if (!ref) {
    return (
      <div className="flex h-full flex-col items-center justify-center gap-2 p-8 text-center">
        <MousePointerClick className="h-5 w-5 text-slate-300" strokeWidth={1.5} />
        <div className="font-medium text-ink">Select a finding</div>
        <p className="max-w-xs text-xs text-ink-muted">
          See the formula, how it compares with its row, what it feeds, and the standard behind it.
        </p>
      </div>
    );
  }

  const rule = finding ? ruleInfo(finding.rule_id) : null;

  return (
    <div className="flex h-full min-h-0 flex-col">
      {/* Header */}
      <div className="border-b border-hairline px-5 py-4">
        <div className="flex flex-wrap items-center gap-1.5">
          {trail.length > 0 && (
            <button
              onClick={back}
              className="mr-1 inline-flex h-6 items-center gap-1 rounded-md px-1.5 text-xs text-ink-muted transition-colors hover:bg-slate-100 hover:text-ink"
            >
              <ArrowLeft className="h-3.5 w-3.5" strokeWidth={1.5} />
              Back
            </button>
          )}
          {finding ? (
            <>
              <Tag>{finding.rule_id}</Tag>
              <SeverityPill severity={finding.severity} />
              {finding.approved && (
                <Tag tone="verified" mono={false}>
                  Accepted
                </Tag>
              )}
              {finding.first_seen !== null && (
                <Tag tone={finding.status === "new" && finding.first_seen > 1 ? "new" : "neutral"} mono={false}>
                  {finding.status === "new" && finding.first_seen > 1 ? "New" : "Seen"} since v{finding.first_seen}
                </Tag>
              )}
            </>
          ) : (
            <Tag tone="info" mono={false}>
              No finding on this cell
            </Tag>
          )}
        </div>
        <div className="mt-2.5 flex items-center gap-2">
          <h2 className="truncate text-[17px] font-semibold text-ink">{rule ? rule.label : "Cell"}</h2>
        </div>
        <div className="mt-1 flex items-center gap-1.5">
          <span className="truncate font-mono text-[13px] text-ink-secondary">{ref}</span>
          <CopyButton text={ref} />
        </div>
      </div>

      {/* Body */}
      <div className="scroll-thin min-h-0 flex-1 overflow-y-auto">
        <AnimatePresence mode="wait" initial={false}>
          <motion.div
            key={ref}
            initial={{ opacity: 0, x: 6 }}
            animate={{ opacity: 1, x: 0 }}
            exit={{ opacity: 0 }}
            transition={{ type: "spring", stiffness: 400, damping: 30 }}
            className="divide-y divide-hairline"
          >
            {finding && rule && (
              <Section title="Why it was flagged">
                <p className="text-[13px] text-ink">{finding.message}</p>
                {rule.why && <p className="mt-2 text-[13px] leading-relaxed text-ink-secondary">{rule.why}</p>}
                {rule.review && (
                  <p className="mt-2.5 rounded-md border border-hairline bg-canvas px-3 py-2 text-xs text-ink-secondary">
                    <span className="font-medium text-ink">To review.</span> {rule.review}
                  </p>
                )}
              </Section>
            )}

            {loading && !cell && (
              <div className="flex items-center gap-2 px-5 py-6 text-xs text-ink-muted">
                <Loader2 className="h-3.5 w-3.5 animate-spin text-accent" strokeWidth={1.5} />
                Reading the cell and its connections
              </div>
            )}

            {error && (
              <div className="px-5 py-4">
                <div className="flex items-start gap-2 rounded-md border border-hairline bg-canvas px-3 py-2.5 text-xs text-ink-secondary">
                  <AlertCircle className="mt-0.5 h-3.5 w-3.5 shrink-0 text-ink-muted" strokeWidth={1.5} />
                  {error}
                </div>
              </div>
            )}

            {cell && cell.ref === ref && (
              <>
                <Section title="The cell">
                  <div className="code-surface overflow-hidden">
                    <div className="flex items-center justify-between border-b border-hairline bg-surface px-3 py-1.5 text-2xs text-ink-muted">
                      <span>{cell.formula ? "Formula" : "Typed value"}</span>
                      <span className="font-mono">{cell.number_format}</span>
                    </div>
                    <div className="break-all px-3 py-2.5 text-[13px] leading-relaxed text-ink">
                      {cell.formula ?? formatValue(cell.value)}
                    </div>
                  </div>
                  {cell.formula && (
                    <div className="mt-2 flex items-baseline justify-between gap-3 text-xs">
                      <span className="text-ink-muted">Value Excel last saved</span>
                      <span className="font-mono tabular-nums text-ink">{formatValue(cell.value)}</span>
                    </div>
                  )}
                </Section>

                <Section title="Its row">
                  <RowCompare cell={cell} ruleId={finding?.rule_id ?? null} />
                </Section>

                <Section title="Dependency trace">
                  <Trace cell={cell} onOpen={openCell} />
                </Section>
              </>
            )}

            {finding && (
              <>
                <Section title="Supporting standard">
                  <Evidence file={run.file} finding={finding} />
                </Section>
                <Section title="Decision">
                  <Decision file={run.file} finding={finding} />
                </Section>
              </>
            )}
          </motion.div>
        </AnimatePresence>
      </div>
    </div>
  );
}

function Section({ title, children, className }: { title: string; children: React.ReactNode; className?: string }) {
  return (
    <section className={cn("px-5 py-4", className)}>
      <div className="eyebrow mb-2.5">{title}</div>
      {children}
    </section>
  );
}

function CopyButton({ text }: { text: string }) {
  const [done, setDone] = React.useState(false);
  return (
    <Tip content={done ? "Copied" : "Copy the reference"}>
      <button
        onClick={async () => {
          try {
            await navigator.clipboard.writeText(text);
            setDone(true);
            setTimeout(() => setDone(false), 1200);
          } catch {
            /* clipboard blocked; nothing to do */
          }
        }}
        className="rounded p-0.5 text-ink-muted transition-colors hover:bg-slate-100 hover:text-ink"
        aria-label="Copy the cell reference"
      >
        {done ? (
          <Check className="h-3.5 w-3.5 text-emerald-600" strokeWidth={1.5} />
        ) : (
          <Copy className="h-3.5 w-3.5" strokeWidth={1.5} />
        )}
      </button>
    </Tip>
  );
}
