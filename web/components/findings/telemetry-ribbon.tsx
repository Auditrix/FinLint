"use client";

import { GitCompareArrows, Network, ShieldAlert, Sigma } from "lucide-react";
import * as React from "react";

import { Tag } from "@/components/ui/pill";
import { Tip } from "@/components/ui/tooltip";
import { SEVERITY_STYLE, scoreBand } from "@/lib/rules";
import { SEVERITY_ORDER, type RunDetail, type Severity } from "@/lib/types";
import { cn, formatInt } from "@/lib/utils";

import { useWorkspace } from "../workspace-context";
import { Sparkline } from "./sparkline";

export function TelemetryRibbon({ run }: { run: RunDetail }) {
  const { history } = useWorkspace();
  const band = scoreBand(run.score);

  const open = run.findings.filter((f) => !f.approved);
  const counts = SEVERITY_ORDER.reduce(
    (acc, s) => ({ ...acc, [s]: open.filter((f) => f.severity === s).length }),
    {} as Record<Severity, number>,
  );
  const accepted = run.findings.length - open.length;
  const newCount = run.findings.filter((f) => f.status === "new").length;

  return (
    <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-4">
      <Metric
        icon={ShieldAlert}
        label="Risk score"
        hint="Computed by rules/score.py from the findings, never by a model, so the same file always scores the same."
      >
        <div className="flex items-end justify-between gap-3">
          <div className="flex items-baseline gap-1">
            <span className="font-display text-[28px] font-bold leading-none tracking-tight text-ink">{run.score}</span>
            <span className="font-mono text-xs text-ink-muted">/ 100</span>
          </div>
          <Sparkline
            values={history.map((h) => h.score)}
            max={100}
            className="h-8 w-28"
            stroke={band.severity === "clean" ? "#16A34A" : "#4F46E5"}
          />
        </div>
        <div className="mt-2.5 flex items-center gap-2">
          {band.severity === "clean" ? (
            <Tag tone="verified" mono={false}>
              {band.label}
            </Tag>
          ) : (
            <span className={cn("text-xs font-medium", SEVERITY_STYLE[band.severity].text)}>{band.label}</span>
          )}
          <span className="text-xs text-ink-muted">set by the worst finding</span>
        </div>
      </Metric>

      <Metric
        icon={Sigma}
        label="Open findings"
        hint="Findings not yet accepted by a person. One per cell: when two checks fire on the same cell, only the more serious is kept."
      >
        <div className="flex items-baseline gap-2">
          <span className="font-display text-[28px] font-bold leading-none tracking-tight text-ink">
            {formatInt(open.length)}
          </span>
          {accepted > 0 && <span className="text-xs text-emerald-600">{accepted} accepted</span>}
        </div>
        <SeverityBar counts={counts} total={open.length} />
      </Metric>

      <Metric
        icon={Network}
        label="Dependency map"
        hint="Every formula parsed and every reference traced, so FinLint knows what each mistake breaks downstream."
      >
        <div className="flex items-baseline gap-2">
          <span className="font-display text-[28px] font-bold leading-none tracking-tight text-ink">
            {formatInt(run.stats.formulas)}
          </span>
          <span className="text-xs text-ink-muted">formulas</span>
        </div>
        <div className="mt-2.5 flex flex-wrap gap-x-3 gap-y-1 font-mono text-2xs text-ink-secondary">
          <span>
            <span className="text-ink">{formatInt(run.stats.links)}</span> links
          </span>
          <span>
            <span className="text-ink">{formatInt(run.stats.cells)}</span> cells
          </span>
          <span>
            <span className="text-ink">{run.stats.sheets}</span> sheets
          </span>
        </div>
      </Metric>

      <Metric
        icon={GitCompareArrows}
        label={run.previous_version ? `Since v${run.previous_version}` : "Version"}
        hint="Compared with the previous check of this file by lineage/diff.py, matching findings on rule, sheet and cell."
      >
        {run.previous_version === null ? (
          <>
            <div className="font-display text-[28px] font-bold leading-none tracking-tight text-ink">v{run.version}</div>
            <div className="mt-2.5 text-xs text-ink-muted">First check of this workbook</div>
          </>
        ) : (
          <>
            <div className="flex items-baseline gap-4">
              <Delta value={newCount} label="new" tone="text-indigo-600" />
              <Delta value={run.resolved.length} label="resolved" tone="text-emerald-600" />
            </div>
            <div className="mt-2.5">
              {run.unchanged_since_previous ? (
                <Tag tone="neutral" mono={false}>
                  Unchanged, identical bytes
                </Tag>
              ) : (
                <span className="text-xs text-ink-muted">The file changed since v{run.previous_version}</span>
              )}
            </div>
          </>
        )}
      </Metric>
    </div>
  );
}

function Metric({
  icon: Icon,
  label,
  hint,
  children,
}: {
  icon: typeof ShieldAlert;
  label: string;
  hint: string;
  children: React.ReactNode;
}) {
  return (
    <div className="panel p-4">
      <Tip content={hint}>
        <div tabIndex={0} className="mb-3 flex w-fit cursor-help items-center gap-1.5 rounded-sm">
          <Icon className="h-3.5 w-3.5 text-ink-muted" strokeWidth={1.5} />
          <span className="eyebrow">{label}</span>
        </div>
      </Tip>
      {children}
    </div>
  );
}

function Delta({ value, label, tone }: { value: number; label: string; tone: string }) {
  return (
    <div className="flex items-baseline gap-1.5">
      <span className={cn("font-display text-[28px] font-bold leading-none tracking-tight", value ? tone : "text-ink")}>
        {formatInt(value)}
      </span>
      <span className="text-xs text-ink-muted">{label}</span>
    </div>
  );
}

function SeverityBar({ counts, total }: { counts: Record<Severity, number>; total: number }) {
  return (
    <div className="mt-2.5">
      <div className="flex h-1.5 overflow-hidden rounded-full bg-recessed">
        {total > 0 &&
          SEVERITY_ORDER.map((s) =>
            counts[s] > 0 ? (
              <div
                key={s}
                className={SEVERITY_STYLE[s].bar}
                style={{ width: `${(counts[s] / total) * 100}%` }}
              />
            ) : null,
          )}
      </div>
      <div className="mt-2 flex flex-wrap gap-x-3 gap-y-1 font-mono text-2xs">
        {SEVERITY_ORDER.map((s) => (
          <span key={s} className={counts[s] ? "text-ink-secondary" : "text-slate-300"}>
            <span className={counts[s] ? "text-ink" : undefined}>{formatInt(counts[s])}</span>{" "}
            {SEVERITY_STYLE[s].label.toLowerCase()}
          </span>
        ))}
      </div>
    </div>
  );
}
