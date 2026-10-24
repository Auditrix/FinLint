"use client";

import * as React from "react";

import { Tip } from "@/components/ui/tooltip";
import type { CellInspect } from "@/lib/types";
import { cn, formatInt, formatValue } from "@/lib/utils";

/**
 * Where two strings differ: the shared start, the differing middle of each,
 * and the shared end. Enough to underline exactly what changed between the
 * row's usual formula shape and this cell's.
 */
function difference(a: string, b: string) {
  let start = 0;
  while (start < a.length && start < b.length && a[start] === b[start]) start++;
  let end = 0;
  while (
    end < a.length - start &&
    end < b.length - start &&
    a[a.length - 1 - end] === b[b.length - 1 - end]
  ) {
    end++;
  }
  return {
    prefix: b.slice(0, start),
    expected: a.slice(start, a.length - end),
    actual: b.slice(start, b.length - end),
    suffix: b.slice(b.length - end),
  };
}

export function RowCompare({ cell, ruleId }: { cell: CellInspect; ruleId: string | null }) {
  const target = cell.row.find((r) => r.is_target);
  const majority = cell.majority_shape;
  // Whole-row counts from the server. Counting the cells shown here instead
  // under-reported on any row wider than the seventeen cell window.
  const formulasInRow = cell.formula_count;
  const matching = cell.majority_count;

  return (
    <div className="space-y-3">
      {/* The row, left to right, around the target */}
      <div className="scroll-thin -mx-1 overflow-x-auto px-1 pb-1">
        <div className="flex min-w-max gap-1.5">
          {cell.row.map((r) => {
            const odd = Boolean(r.shape && majority && r.shape !== majority);
            const typed = r.shape === null && r.value !== null;
            return (
              <Tip
                key={r.coordinate}
                content={
                  <span className="font-mono">
                    {r.coordinate}: {r.formula ?? formatValue(r.value)}
                  </span>
                }
              >
                <div
                  tabIndex={0}
                  aria-label={`${r.coordinate}: ${r.formula ?? formatValue(r.value)}`}
                  className={cn(
                    "w-[5.5rem] shrink-0 rounded-md border px-2 py-1.5",
                    r.is_target ? "border-accent bg-accent-soft" : "border-hairline bg-surface",
                  )}
                >
                  <div className="flex items-center justify-between">
                    <span className={cn("font-mono text-2xs", r.is_target ? "text-accent" : "text-ink-muted")}>
                      {r.coordinate}
                    </span>
                    {odd && <span className="h-1.5 w-1.5 rounded-full bg-orange-500" aria-label="different shape" />}
                    {typed && !r.is_target && formulasInRow > 0 && (
                      <span className="h-1.5 w-1.5 rounded-full bg-slate-300" aria-label="typed value" />
                    )}
                  </div>
                  <div className="mt-0.5 truncate font-mono text-xs text-ink">
                    {r.shape ?? <span className="text-ink-secondary">{formatValue(r.value)}</span>}
                  </div>
                </div>
              </Tip>
            );
          })}
        </div>
      </div>
      {cell.row_total > cell.row.length && (
        <p className="font-mono text-2xs text-ink-muted">
          Showing {cell.row.length} of {formatInt(cell.row_total)} cells in row {target?.coordinate.replace(/[A-Z]+/, "")}
        </p>
      )}

      {/* The comparison that matters for each rule */}
      {ruleId === "formula_drift" && majority && target?.shape && target.shape !== majority && (
        <ShapeDiff expected={majority} actual={target.shape} matching={matching} />
      )}

      {ruleId === "hardcoded_value" && target && target.shape === null && (
        <div className="rounded-md border border-hairline bg-slate-900 p-3 font-mono text-xs leading-relaxed">
          <div className="text-slate-400">
            {formatInt(formulasInRow)} cells in this row are calculated
            {majority ? (
              <>
                , most as <span className="text-slate-100">{majority}</span>
              </>
            ) : null}
          </div>
          <div className="mt-1.5 text-slate-400">
            {target.coordinate} holds a typed{" "}
            <span className="text-red-300 underline decoration-red-400 decoration-wavy underline-offset-4">
              {formatValue(target.value)}
            </span>
          </div>
        </div>
      )}
    </div>
  );
}

function ShapeDiff({ expected, actual, matching }: { expected: string; actual: string; matching: number }) {
  const d = difference(expected, actual);
  return (
    <div className="overflow-hidden rounded-md border border-slate-800 bg-slate-900 font-mono text-xs">
      <div className="flex items-center justify-between border-b border-slate-800 px-3 py-1.5 text-2xs text-slate-400">
        <span>Formula shape, references shown as #</span>
        <span className="tabular-nums">{matching} cells share the usual shape</span>
      </div>
      <div className="grid grid-cols-[auto_1fr] gap-x-4 gap-y-1.5 px-3 py-2.5">
        <span className="text-slate-500">usual</span>
        <span className="break-all text-emerald-300">
          {d.prefix}
          <span className="rounded-sm bg-emerald-400/15 px-0.5">{d.expected || "∅"}</span>
          {d.suffix}
        </span>
        <span className="text-slate-500">this cell</span>
        <span className="break-all text-slate-100">
          {d.prefix}
          <span className="rounded-sm bg-red-400/15 px-0.5 text-red-300 underline decoration-red-400 decoration-wavy underline-offset-4">
            {d.actual || "∅"}
          </span>
          {d.suffix}
        </span>
      </div>
    </div>
  );
}
