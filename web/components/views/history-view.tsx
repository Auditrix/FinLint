"use client";

import { CheckCircle2, CirclePlus } from "lucide-react";
import * as React from "react";
import {
  Area,
  AreaChart,
  Bar,
  BarChart,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import { SeverityPill, Tag } from "@/components/ui/pill";
import { ruleInfo, SEVERITY_STYLE } from "@/lib/rules";
import { SEVERITY_ORDER } from "@/lib/types";
import { cellRef, cn, formatInt, formatTimestamp, shortSha } from "@/lib/utils";

import { useWorkspace } from "../workspace-context";
import { PageHeader } from "./page-header";

const AXIS = { fontSize: 11, fill: "#64748B", fontFamily: "var(--font-mono)" };
const BAR_FILL: Record<string, string> = { critical: "#EF4444", high: "#F97316", medium: "#FBBF24", low: "#CBD5E1" };

export function HistoryView() {
  const { run, history, setView, select } = useWorkspace();
  if (!run) return null;

  const data = history.map((h) => ({ version: `v${h.version}`, score: h.score, ...h.counts }));
  const newFindings = run.findings.filter((f) => f.status === "new" && run.previous_version !== null);

  return (
    <div className="scroll-thin h-full overflow-y-auto">
      <div className="space-y-4 p-5">
        <PageHeader
          title="Version history"
          description={`Every check of ${run.file}, kept with the hash of the exact bytes checked. A finding is matched across versions on its rule, sheet and cell.`}
        />

        <div className="grid grid-cols-1 gap-4 xl:grid-cols-2">
          <ChartPanel title="Risk score by version" note="0 to 100, set by the worst finding">
            {history.length < 2 ? (
              <OneVersion />
            ) : (
              <ResponsiveContainer width="100%" height="100%">
                <AreaChart data={data} margin={{ top: 8, right: 12, bottom: 0, left: -18 }}>
                  <defs>
                    <linearGradient id="score-fill" x1="0" y1="0" x2="0" y2="1">
                      <stop offset="0%" stopColor="#4F46E5" stopOpacity={0.14} />
                      <stop offset="100%" stopColor="#4F46E5" stopOpacity={0} />
                    </linearGradient>
                  </defs>
                  <CartesianGrid stroke="#E2E8F0" vertical={false} />
                  <XAxis dataKey="version" tick={AXIS} axisLine={false} tickLine={false} />
                  <YAxis domain={[0, 100]} ticks={[0, 25, 50, 75, 100]} tick={AXIS} axisLine={false} tickLine={false} />
                  <Tooltip content={<ChartTip />} />
                  <Area
                    type="monotone"
                    dataKey="score"
                    stroke="#4F46E5"
                    strokeWidth={1.5}
                    fill="url(#score-fill)"
                    dot={{ r: 2.5, fill: "#4F46E5", strokeWidth: 0 }}
                    activeDot={{ r: 3.5 }}
                    isAnimationActive={false}
                  />
                </AreaChart>
              </ResponsiveContainer>
            )}
          </ChartPanel>

          <ChartPanel title="Findings by severity" note="One finding per cell">
            {history.length < 2 ? (
              <OneVersion />
            ) : (
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={data} margin={{ top: 8, right: 12, bottom: 0, left: -6 }} barCategoryGap="38%">
                  <CartesianGrid stroke="#E2E8F0" vertical={false} />
                  <XAxis dataKey="version" tick={AXIS} axisLine={false} tickLine={false} />
                  <YAxis tick={AXIS} axisLine={false} tickLine={false} tickFormatter={(v: number) => formatInt(v)} />
                  <Tooltip content={<ChartTip />} cursor={{ fill: "#F1F5F9" }} />
                  {SEVERITY_ORDER.map((s) => (
                    <Bar key={s} dataKey={s} stackId="sev" fill={BAR_FILL[s]} isAnimationActive={false} />
                  ))}
                </BarChart>
              </ResponsiveContainer>
            )}
          </ChartPanel>
        </div>

        <section className="panel overflow-hidden">
          <div className="border-b border-hairline px-4 py-3">
            <div className="eyebrow">Versions</div>
          </div>
          <div className="scroll-thin overflow-x-auto">
            <table className="w-full border-separate border-spacing-0 text-left">
              <thead>
                <tr className="bg-recessed">
                  {["Version", "Checked", "Score", "Findings", ...SEVERITY_ORDER.map((s) => SEVERITY_STYLE[s].label), "SHA-256"].map(
                    (h, i) => (
                      <th
                        key={h}
                        className={cn("eyebrow border-b border-hairline px-4 py-2 font-medium", i >= 2 && i <= 7 && "text-right")}
                      >
                        {h}
                      </th>
                    ),
                  )}
                </tr>
              </thead>
              <tbody>
                {[...history].reverse().map((h, i, list) => {
                  const older = list[i + 1];
                  const same = older ? older.sha256 === h.sha256 : false;
                  return (
                    <tr key={h.run_id} className="hover:bg-slate-50/80">
                      <td className="border-b border-hairline px-4 py-2.5">
                        <div className="flex items-center gap-2">
                          <span className="font-mono text-[13px] font-medium text-ink">v{h.version}</span>
                          {h.version === run.version && (
                            <Tag tone="accent" mono={false}>
                              Latest
                            </Tag>
                          )}
                        </div>
                      </td>
                      <td className="whitespace-nowrap border-b border-hairline px-4 py-2.5 text-xs text-ink-secondary">
                        {formatTimestamp(h.created_at)}
                      </td>
                      <Num>{h.score}</Num>
                      <Num>{formatInt(h.total)}</Num>
                      {SEVERITY_ORDER.map((s) => (
                        <Num key={s} muted={h.counts[s] === 0}>
                          {formatInt(h.counts[s])}
                        </Num>
                      ))}
                      <td className="border-b border-hairline px-4 py-2.5">
                        <div className="flex items-center gap-2">
                          <span className="font-mono text-xs text-ink-secondary">{shortSha(h.sha256)}</span>
                          {same && (
                            <Tag tone="neutral" mono={false} className="py-0 text-2xs">
                              same bytes as v{older?.version}
                            </Tag>
                          )}
                        </div>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </section>

        {run.previous_version !== null && (
          <div className="grid grid-cols-1 gap-4 xl:grid-cols-2">
            <ChangeList
              title={`New in v${run.version}`}
              icon={<CirclePlus className="h-3.5 w-3.5 text-indigo-600" strokeWidth={1.5} />}
              empty={`Nothing new since v${run.previous_version}.`}
              items={newFindings.map((f) => ({ ...f, ref: cellRef(f.sheet, f.coordinate) }))}
              onOpen={(ref) => {
                setView("findings");
                select(ref);
              }}
            />
            <ChangeList
              title={`Resolved since v${run.previous_version}`}
              icon={<CheckCircle2 className="h-3.5 w-3.5 text-emerald-600" strokeWidth={1.5} />}
              empty={`Nothing resolved since v${run.previous_version}.`}
              items={run.resolved.map((f) => ({ ...f, ref: cellRef(f.sheet, f.coordinate) }))}
            />
          </div>
        )}
      </div>
    </div>
  );
}

function ChartPanel({ title, note, children }: { title: string; note: string; children: React.ReactNode }) {
  return (
    <section className="panel p-4">
      <div className="mb-3 flex items-baseline justify-between">
        <span className="eyebrow">{title}</span>
        <span className="text-2xs text-ink-muted">{note}</span>
      </div>
      <div className="h-48">{children}</div>
    </section>
  );
}

function OneVersion() {
  return (
    <div className="flex h-full items-center justify-center text-xs text-ink-muted">
      One version so far. Check the workbook again to see a trend.
    </div>
  );
}

function Num({ children, muted }: { children: React.ReactNode; muted?: boolean }) {
  return (
    <td
      className={cn(
        "border-b border-hairline px-4 py-2.5 text-right font-mono text-xs tabular-nums",
        muted ? "text-slate-300" : "text-ink",
      )}
    >
      {children}
    </td>
  );
}

function ChangeList({
  title,
  icon,
  empty,
  items,
  onOpen,
}: {
  title: string;
  icon: React.ReactNode;
  empty: string;
  items: { rule_id: string; severity: (typeof SEVERITY_ORDER)[number]; ref: string }[];
  onOpen?: (ref: string) => void;
}) {
  return (
    <section className="panel overflow-hidden">
      <div className="flex items-center gap-2 border-b border-hairline px-4 py-3">
        {icon}
        <span className="eyebrow">{title}</span>
        <span className="ml-auto font-mono text-2xs text-ink-muted">{formatInt(items.length)}</span>
      </div>
      {items.length === 0 ? (
        <p className="px-4 py-6 text-center text-xs text-ink-muted">{empty}</p>
      ) : (
        <ul className="scroll-thin max-h-72 divide-y divide-hairline overflow-y-auto">
          {items.map((f) => (
            <li key={`${f.rule_id}|${f.ref}`}>
              <button
                disabled={!onOpen}
                onClick={() => onOpen?.(f.ref)}
                className="flex w-full items-center gap-3 px-4 py-2 text-left transition-colors enabled:hover:bg-slate-50/80"
              >
                <SeverityPill severity={f.severity} />
                <span className="font-mono text-xs text-ink">{f.ref}</span>
                <span className="truncate text-xs text-ink-muted">{ruleInfo(f.rule_id).label}</span>
              </button>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}

function ChartTip({
  active,
  payload,
  label,
}: {
  active?: boolean;
  payload?: { name: string; value: number; color?: string }[];
  label?: string;
}) {
  if (!active || !payload?.length) return null;
  return (
    <div className="rounded-md border border-hairline bg-surface px-3 py-2 shadow-overlay">
      <div className="font-mono text-xs font-medium text-ink">{label}</div>
      {payload.map((p) => (
        <div key={p.name} className="mt-1 flex items-center justify-between gap-4 text-2xs">
          <span className="capitalize text-ink-secondary">{p.name}</span>
          <span className="font-mono tabular-nums text-ink">{formatInt(p.value)}</span>
        </div>
      ))}
    </div>
  );
}
