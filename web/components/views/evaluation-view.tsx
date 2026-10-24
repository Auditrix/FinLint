"use client";

import { AlertTriangle, FileCode2, Loader2 } from "lucide-react";
import * as React from "react";

import { Tip } from "@/components/ui/tooltip";
import * as api from "@/lib/api";
import { ruleInfo } from "@/lib/rules";
import type { EvaluationReport, EvaluationTier } from "@/lib/types";
import { cn, formatInt, formatPercent } from "@/lib/utils";

import { PageHeader } from "./page-header";

export function EvaluationView() {
  const [report, setReport] = React.useState<EvaluationReport | null>(null);
  const [error, setError] = React.useState<string | null>(null);

  React.useEffect(() => {
    api
      .getEvaluation()
      .then(setReport)
      .catch((e) => setError(e instanceof Error ? e.message : "Could not load the results."));
  }, []);

  if (error) {
    return <div className="p-5 text-[13px] text-ink-secondary">{error}</div>;
  }
  if (!report) {
    return (
      <div className="flex items-center gap-2 p-5 text-xs text-ink-muted">
        <Loader2 className="h-3.5 w-3.5 animate-spin text-accent" strokeWidth={1.5} />
        Loading results
      </div>
    );
  }

  const [one, two, three] = report.tiers;

  return (
    <div className="scroll-thin h-full overflow-y-auto">
      <div className="space-y-4 p-5">
        <PageHeader
          title="Evaluation"
          description="Measured, not claimed. Three tiers, each harder to flatter than the last, and the bad numbers are shown as plainly as the good ones."
        />

        <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">
          {report.tiers.map((t) => (
            <TierCard key={t.tier} tier={t} />
          ))}
        </div>

        <div className="grid grid-cols-1 gap-4 xl:grid-cols-2">
          {two && <TierTwoDetail tier={two} />}
          {three && <TierThreeDetail tier={three} />}
        </div>

        <div className="grid grid-cols-1 gap-4 xl:grid-cols-[1fr_22rem]">
          <Retrieval report={report} />
          <Comparison report={report} tierOnePrecision={one?.precision ?? null} tierTwoPrecision={two?.precision ?? null} />
        </div>

        <p className="flex items-center gap-1.5 text-2xs text-ink-muted">
          <FileCode2 className="h-3 w-3" strokeWidth={1.5} />
          {report.source}
        </p>
      </div>
    </div>
  );
}

function TierCard({ tier }: { tier: EvaluationTier }) {
  const unlabelled = tier.precision === null || tier.recall === null;
  return (
    <section className={cn("panel flex flex-col p-4", tier.tier === 2 && "border-amber-200")}>
      <div className="flex items-center justify-between">
        <span className="eyebrow">Tier {tier.tier}</span>
        <span className="truncate font-mono text-2xs text-ink-muted">{tier.script}</span>
      </div>
      <h3 className="mt-1.5 text-[15px] font-semibold text-ink">{tier.name}</h3>
      <p className="mt-0.5 text-xs text-ink-muted">{tier.dataset}</p>

      {unlabelled ? (
        <div className="mt-4 flex items-end gap-6">
          <Big value={formatPercent(tier.trigger_rate ?? 0)} label="files triggered" />
          <div className="pb-1 text-xs text-ink-muted">No answer key exists, so no precision or recall</div>
        </div>
      ) : (
        <div className="mt-4 flex items-end gap-6">
          <Big value={formatPercent(tier.precision!)} label="precision" tone={tier.precision! < 0.2 ? "bad" : undefined} />
          <Big value={formatPercent(tier.recall!)} label="recall" tone={tier.recall! < 0.2 ? "bad" : undefined} />
        </div>
      )}

      <p className="mt-4 border-t border-hairline pt-3 text-[13px] leading-relaxed text-ink-secondary">{tier.reading}</p>
    </section>
  );
}

function Big({ value, label, tone }: { value: string; label: string; tone?: "bad" }) {
  return (
    <div>
      <div
        className={cn(
          "font-display text-[26px] font-bold leading-none tracking-tight tabular-nums",
          tone === "bad" ? "text-red-600" : "text-ink",
        )}
      >
        {value}
      </div>
      <div className="mt-1 text-2xs text-ink-muted">{label}</div>
    </div>
  );
}

function TierTwoDetail({ tier }: { tier: EvaluationTier }) {
  const tp = tier.true_positives ?? 0;
  const fp = tier.false_positives ?? 0;
  const deadInput = tier.dead_input_false_positives ?? 0;
  return (
    <section className="panel p-4">
      <div className="flex items-center gap-2">
        <AlertTriangle className="h-3.5 w-3.5 text-amber-600" strokeWidth={1.5} />
        <span className="eyebrow">Tier 2, read this one carefully</span>
      </div>
      <p className="mt-2 text-[13px] leading-relaxed text-ink-secondary">
        On somebody else&apos;s labelled data, run untouched, the engine made{" "}
        <span className="font-mono text-ink">{formatInt(tp)}</span> correct findings and{" "}
        <span className="font-mono text-ink">{formatInt(fp)}</span> wrong ones.
      </p>

      <div className="mt-4 space-y-2.5">
        <Proportion label="correct" value={tp} total={tp + fp} className="bg-emerald-500" />
        <Proportion label="wrong" value={fp} total={tp + fp} className="bg-red-400" />
        {deadInput > 0 && (
          <Proportion label="wrong, from dead_input alone" value={deadInput} total={tp + fp} className="bg-red-300" />
        )}
      </div>

      <p className="mt-4 border-t border-hairline pt-3 text-xs leading-relaxed text-ink-muted">
        One rule causes most of it. <span className="font-mono">dead_input</span> finds genuine unused inputs that this
        answer key does not count as bugs, so part of the gap is a definition mismatch rather than a detector fault.
        Separating the two is unfinished work.
      </p>
    </section>
  );
}

function Proportion({ label, value, total, className }: { label: string; value: number; total: number; className: string }) {
  const share = total ? value / total : 0;
  return (
    <div>
      <div className="mb-1 flex items-baseline justify-between text-xs">
        <span className="text-ink-secondary">{label}</span>
        <span className="font-mono tabular-nums text-ink">
          {formatInt(value)} <span className="text-ink-muted">· {formatPercent(share)}</span>
        </span>
      </div>
      <div className="h-1.5 overflow-hidden rounded-full bg-recessed">
        <div className={cn("h-full rounded-full", className)} style={{ width: `${Math.max(share * 100, value ? 0.6 : 0)}%` }} />
      </div>
    </div>
  );
}

function TierThreeDetail({ tier }: { tier: EvaluationTier }) {
  const top = Math.max(...(tier.by_rule ?? []).map((r) => r.share), 0.01);
  return (
    <section className="panel p-4">
      <div className="flex items-baseline justify-between">
        <span className="eyebrow">Tier 3, the real target</span>
        <span className="font-mono text-2xs text-ink-muted">
          {formatInt(tier.scanned ?? 0)} files · {tier.failed_to_parse} failed to parse
        </span>
      </div>

      <div className="mt-3 grid grid-cols-3 gap-2">
        {(["median", "mean", "max"] as const).map((k) => (
          <div key={k} className="rounded-md border border-hairline bg-canvas px-2.5 py-2">
            <div className="text-2xs text-ink-muted">findings per file, {k}</div>
            <div className="mt-0.5 font-mono text-[15px] font-medium tabular-nums text-ink">
              {tier.findings_per_workbook?.[k]}
            </div>
          </div>
        ))}
      </div>

      <div className="mt-4 space-y-2">
        {(tier.by_rule ?? []).map((r) => (
          <div key={r.rule_id} className="grid grid-cols-[9rem_1fr_4.5rem] items-center gap-3">
            <span className="truncate text-xs text-ink-secondary">{ruleInfo(r.rule_id).label}</span>
            <div className="h-1.5 overflow-hidden rounded-full bg-recessed">
              <div className="h-full rounded-full bg-accent" style={{ width: `${(r.share / top) * 100}%` }} />
            </div>
            <span className="text-right font-mono text-2xs tabular-nums text-ink">
              {r.workbooks} <span className="text-ink-muted">· {formatPercent(r.share)}</span>
            </span>
          </div>
        ))}
      </div>

      <p className="mt-4 border-t border-hairline pt-3 text-xs leading-relaxed text-ink-muted">
        A median of one finding per file is the encouraging part: a tool that shouts about every file is one people stop
        opening. Still owed: a hand audit of 30 sampled files, so there is no false positive estimate yet.
      </p>
    </section>
  );
}

function Retrieval({ report }: { report: EvaluationReport }) {
  const r = report.retrieval;
  const ks = r.documents.map((d) => d.k);
  return (
    <section className="panel p-4">
      <div className="flex items-baseline justify-between">
        <span className="eyebrow">Retrieval</span>
        <span className="font-mono text-2xs text-ink-muted">
          {r.questions} questions · {formatInt(r.corpus_chunks)} chunks
        </span>
      </div>
      <p className="mt-2 text-[13px] text-ink-secondary">
        Does searching the rule corpus return the passage that should come back?
      </p>

      <table className="mt-4 w-full border-separate border-spacing-0 text-left">
        <thead>
          <tr>
            <th className="eyebrow border-b border-hairline pb-2 font-medium">Correct</th>
            {ks.map((k) => (
              <th key={k} className="eyebrow border-b border-hairline pb-2 text-right font-medium">
                Top {k}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {([
            ["document", r.documents],
            ["passage", r.passages],
          ] as const).map(([label, rows]) => (
            <tr key={label}>
              <td className="border-b border-hairline py-2.5 text-[13px] text-ink">{label}</td>
              {rows.map((row) => (
                <td key={row.k} className="border-b border-hairline py-2.5 text-right">
                  <div className="font-mono text-[13px] tabular-nums text-ink">
                    {row.hits}/{r.questions}
                  </div>
                  <div className="font-mono text-2xs tabular-nums text-ink-muted">{formatPercent(row.hits / r.questions, 0)}</div>
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>

      <p className="mt-3 text-xs leading-relaxed text-ink-muted">{r.caveat}</p>
    </section>
  );
}

function Comparison({
  report,
  tierOnePrecision,
  tierTwoPrecision,
}: {
  report: EvaluationReport;
  tierOnePrecision: number | null;
  tierTwoPrecision: number | null;
}) {
  const custodes = report.comparison.find((c) => c.value !== undefined);
  const auditors = report.comparison.find((c) => c.range !== undefined);
  return (
    <section className="panel p-4">
      <span className="eyebrow">Against published tools</span>
      <div className="mt-3 space-y-3">
        <Row label="FinLint, own planted faults" value={tierOnePrecision} hint="Tier 1. Flattering by design, since we planted the faults." />
        <Row label="FinLint, outside answer key" value={tierTwoPrecision} bad hint="Tier 2. The honest comparison." />
        {custodes?.value !== undefined && (
          <Row label="CUSTODES, measured by ExceLint" value={custodes.value} hint={custodes.label} />
        )}
      </div>
      {auditors?.range && (
        <p className="mt-4 border-t border-hairline pt-3 text-xs leading-relaxed text-ink-muted">
          Published spreadsheet auditors run at{" "}
          <span className="font-mono text-ink">
            {formatPercent(auditors.range[0], 0)} to {formatPercent(auditors.range[1], 0)}
          </span>{" "}
          false positives. On outside data FinLint is below even that bar, and says so.
        </p>
      )}
    </section>
  );
}

function Row({ label, value, bad, hint }: { label: string; value: number | null; bad?: boolean; hint: string }) {
  if (value === null) return null;
  return (
    <Tip content={hint} side="left">
      <div className="cursor-help">
        <div className="mb-1 flex items-baseline justify-between text-xs">
          <span className="text-ink-secondary">{label}</span>
          <span className={cn("font-mono tabular-nums", bad ? "text-red-600" : "text-ink")}>{formatPercent(value)}</span>
        </div>
        <div className="h-1.5 overflow-hidden rounded-full bg-recessed">
          <div
            className={cn("h-full rounded-full", bad ? "bg-red-400" : "bg-slate-400")}
            style={{ width: `${Math.max(value * 100, 0.6)}%` }}
          />
        </div>
      </div>
    </Tip>
  );
}
