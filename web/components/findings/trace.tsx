"use client";

import { ArrowDownToLine, ArrowUpFromLine, Waves } from "lucide-react";

import type { CellInspect } from "@/lib/types";
import { cn, formatInt, splitRef } from "@/lib/utils";

/**
 * The dependency trace for one cell, straight from graph/analyse.py.
 * "Reads" is precedents, "Read by" is dependents, and the downstream count is
 * the blast radius: everything that would change if this cell were wrong.
 */
export function Trace({ cell, onOpen }: { cell: CellInspect; onOpen: (ref: string) => void }) {
  return (
    <div className="space-y-3">
      <div className="grid grid-cols-3 gap-2">
        <Count icon={ArrowDownToLine} value={cell.precedents_total} label="reads" />
        <Count icon={ArrowUpFromLine} value={cell.dependents_total} label="read by" />
        <Count icon={Waves} value={cell.blast_radius} label="downstream" strong />
      </div>
      <RefList title="Reads" refs={cell.precedents} total={cell.precedents_total} home={cell.sheet} onOpen={onOpen} />
      <RefList title="Read by" refs={cell.dependents} total={cell.dependents_total} home={cell.sheet} onOpen={onOpen} />
    </div>
  );
}

function Count({
  icon: Icon,
  value,
  label,
  strong,
}: {
  icon: typeof Waves;
  value: number;
  label: string;
  strong?: boolean;
}) {
  return (
    <div className="rounded-md border border-hairline bg-canvas px-2.5 py-2">
      <div className="flex items-center gap-1 text-2xs text-ink-muted">
        <Icon className="h-3 w-3" strokeWidth={1.5} />
        {label}
      </div>
      <div className={cn("mt-0.5 font-mono text-[15px] font-medium tabular-nums", strong ? "text-trace" : "text-ink")}>
        {formatInt(value)}
      </div>
    </div>
  );
}

function RefList({
  title,
  refs,
  total,
  home,
  onOpen,
}: {
  title: string;
  refs: string[];
  total: number;
  home: string;
  onOpen: (ref: string) => void;
}) {
  if (total === 0) return null;
  return (
    <div>
      <div className="eyebrow mb-1.5">{title}</div>
      <div className="flex flex-wrap gap-1">
        {refs.map((ref) => {
          const { sheet, coordinate } = splitRef(ref);
          // Same sheet references are shown bare, the way Excel writes them.
          const label = sheet === home ? coordinate : ref;
          return (
            <button
              key={ref}
              onClick={() => onOpen(ref)}
              className="rounded border border-sky-200 bg-sky-50 px-1.5 py-0.5 font-mono text-2xs text-sky-700 transition-colors hover:border-sky-300 hover:bg-sky-100"
              title={ref}
            >
              {label}
            </button>
          );
        })}
        {total > refs.length && (
          <span className="px-1 py-0.5 font-mono text-2xs text-ink-muted">+{formatInt(total - refs.length)} more</span>
        )}
      </div>
    </div>
  );
}
