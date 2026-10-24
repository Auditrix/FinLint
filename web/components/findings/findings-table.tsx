"use client";

import { motion } from "framer-motion";
import { CheckCircle2, ChevronLeft, ChevronRight } from "lucide-react";
import * as React from "react";

import { SeverityPill, Tag } from "@/components/ui/pill";
import { Tip } from "@/components/ui/tooltip";
import { CATEGORIES, ruleInfo } from "@/lib/rules";
import { SEVERITY_ORDER, type AnnotatedFinding, type Severity } from "@/lib/types";
import { cellRef, cn, formatInt } from "@/lib/utils";

const PAGE = 50;

export interface Filters {
  severity: Severity | "all";
  category: (typeof CATEGORIES)[number] | "all";
  showAccepted: boolean;
}

export function applyFilters(findings: AnnotatedFinding[], filters: Filters): AnnotatedFinding[] {
  return findings.filter(
    (f) =>
      (filters.severity === "all" || f.severity === filters.severity) &&
      (filters.category === "all" || ruleInfo(f.rule_id).category === filters.category) &&
      (filters.showAccepted || !f.approved),
  );
}

export function FindingsTable({
  findings,
  visible,
  filters,
  onFilters,
  selected,
  onSelect,
}: {
  findings: AnnotatedFinding[];
  visible: AnnotatedFinding[];
  filters: Filters;
  onFilters: (f: Filters) => void;
  selected: string | null;
  onSelect: (ref: string) => void;
}) {
  const [pageWanted, setPage] = React.useState(0);
  const pages = Math.max(1, Math.ceil(visible.length / PAGE));
  // Clamped on every render. Accepting the only finding on the last page used
  // to leave the table on a page that no longer existed: "Nothing here", with
  // a footer reading "51 to 50 of 50".
  const page = Math.min(pageWanted, pages - 1);
  const rows = visible.slice(page * PAGE, page * PAGE + PAGE);
  const scroller = React.useRef<HTMLDivElement>(null);

  // Filtering resets to the first page so the list never looks empty.
  React.useEffect(() => setPage(0), [filters]);

  // Keep the selected row on the current page when it was chosen elsewhere,
  // for example from the command palette.
  React.useEffect(() => {
    if (!selected) return;
    const at = visible.findIndex((f) => cellRef(f.sheet, f.coordinate) === selected);
    if (at >= 0) setPage(Math.floor(at / PAGE));
  }, [selected, visible]);

  // Every filter except severity itself, so each tab's count is exactly how
  // many rows clicking it would show.
  const base = applyFilters(findings, { ...filters, severity: "all" });
  const severityCount = (s: Severity | "all") => (s === "all" ? base.length : base.filter((f) => f.severity === s).length);

  function onKey(e: React.KeyboardEvent) {
    if (e.key !== "ArrowDown" && e.key !== "ArrowUp" && e.key !== "j" && e.key !== "k") return;
    e.preventDefault();
    const at = visible.findIndex((f) => cellRef(f.sheet, f.coordinate) === selected);
    const down = e.key === "ArrowDown" || e.key === "j";
    const next = visible[Math.min(visible.length - 1, Math.max(0, at + (down ? 1 : -1)))];
    if (next) onSelect(cellRef(next.sheet, next.coordinate));
  }

  return (
    <div className="flex h-full min-h-0 flex-col">
      {/* Filters */}
      <div className="flex flex-wrap items-center gap-x-4 gap-y-2 border-b border-hairline px-4 py-2.5">
        <div className="flex items-center rounded-md border border-hairline bg-recessed p-0.5">
          {(["all", ...SEVERITY_ORDER] as const).map((s) => {
            const active = filters.severity === s;
            const count = severityCount(s);
            return (
              <button
                key={s}
                aria-pressed={active}
                onClick={() => onFilters({ ...filters, severity: s })}
                className={cn(
                  "relative flex h-6 items-center gap-1.5 rounded px-2 text-xs transition-colors",
                  active ? "text-ink" : "text-ink-muted hover:text-ink",
                  count === 0 && !active && "opacity-50",
                )}
              >
                {active && (
                  <motion.span
                    layoutId="severity-tab"
                    transition={{ type: "spring", stiffness: 400, damping: 30 }}
                    className="absolute inset-0 rounded border border-hairline bg-surface shadow-hairline"
                  />
                )}
                <span className="relative capitalize">{s}</span>
                <span className="relative font-mono text-2xs text-ink-muted">{formatInt(count)}</span>
              </button>
            );
          })}
        </div>

        <div className="flex items-center gap-1">
          {(["all", ...CATEGORIES] as const).map((c) => (
            <button
              key={c}
              aria-pressed={filters.category === c}
              onClick={() => onFilters({ ...filters, category: c })}
              className={cn(
                "h-6 rounded-md px-2 text-xs transition-colors",
                filters.category === c ? "bg-slate-100 text-ink" : "text-ink-muted hover:text-ink",
              )}
            >
              {c === "all" ? "All checks" : c}
            </button>
          ))}
        </div>

        <label className="ml-auto flex cursor-pointer items-center gap-1.5 text-xs text-ink-muted">
          <input
            type="checkbox"
            checked={filters.showAccepted}
            onChange={(e) => onFilters({ ...filters, showAccepted: e.target.checked })}
            className="h-3.5 w-3.5 rounded border-slate-300 accent-indigo-600"
          />
          Show accepted
        </label>
      </div>

      {/* Table */}
      <div
        ref={scroller}
        tabIndex={0}
        onKeyDown={onKey}
        className="scroll-thin min-h-0 flex-1 overflow-auto outline-none"
        aria-label="Findings. Arrow keys or j and k to move."
      >
        <table className="w-full border-separate border-spacing-0 text-left">
          <thead className="sticky top-0 z-10">
            <tr className="bg-recessed/95 backdrop-blur">
              <Th className="pl-4">Finding</Th>
              <Th className="w-[1%]">Location</Th>
              <Th className="w-[1%] text-right">
                <Tip content="Cells downstream that read this one, directly or through other formulas.">
                  <span tabIndex={0} className="cursor-help rounded-sm">
                    Impact
                  </span>
                </Tip>
              </Th>
              <Th className="w-[1%] pr-4">Severity</Th>
            </tr>
          </thead>
          <tbody>
            {rows.map((f) => {
              const ref = cellRef(f.sheet, f.coordinate);
              const active = ref === selected;
              const rule = ruleInfo(f.rule_id);
              return (
                <tr
                  key={`${f.rule_id}|${ref}`}
                  onClick={() => onSelect(ref)}
                  className={cn(
                    "group cursor-pointer transition-colors",
                    active ? "bg-indigo-50/40" : "hover:bg-slate-50/80",
                    f.approved && "opacity-60",
                  )}
                >
                  {/* w-full with max-w-0 lets this column take whatever width is
                      left and truncate inside it. Without it, nowrap text sets the
                      column's minimum to the whole message and the table overflows. */}
                  <Td className={cn("w-full min-w-[13rem] max-w-0 pl-4", active && "shadow-[inset_2px_0_0_#4F46E5]")}>
                    <div className="flex items-center gap-1.5">
                      <span className="truncate font-medium text-ink">{rule.label}</span>
                      {f.status === "new" && f.first_seen !== null && f.first_seen > 1 && (
                        <Tag tone="new" className="shrink-0 px-1.5 py-0 text-2xs">
                          new in v{f.first_seen}
                        </Tag>
                      )}
                      {f.approved && (
                        <CheckCircle2 className="h-3.5 w-3.5 shrink-0 text-emerald-600" strokeWidth={1.5} />
                      )}
                    </div>
                    {/* The rule id and the label say the same thing, so the id is a
                        caption rather than its own column. */}
                    <div className="mt-0.5 flex min-w-0 items-baseline gap-1.5 text-xs">
                      <span className="shrink-0 font-mono text-2xs text-ink-muted">{f.rule_id}</span>
                      <span className="truncate text-ink-muted">{f.message}</span>
                    </div>
                  </Td>
                  <Td>
                    <div className="flex items-center gap-1.5 whitespace-nowrap">
                      <span className="max-w-[9rem] truncate rounded border border-hairline bg-surface px-1.5 py-0.5 text-2xs text-ink-secondary">
                        {f.sheet}
                      </span>
                      <span className="font-mono text-xs text-ink">{f.coordinate}</span>
                    </div>
                  </Td>
                  <Td className="text-right font-mono text-xs tabular-nums text-ink-secondary">
                    {f.blast_radius > 0 ? formatInt(f.blast_radius) : <span className="text-slate-300">0</span>}
                  </Td>
                  <Td className="pr-4">
                    <SeverityPill severity={f.severity} />
                  </Td>
                </tr>
              );
            })}
          </tbody>
        </table>

        {rows.length === 0 && (
          <div className="px-6 py-14 text-center">
            <div className="font-medium text-ink">Nothing here</div>
            <div className="mt-1 text-xs text-ink-muted">No findings match these filters.</div>
          </div>
        )}
      </div>

      {/* Footer */}
      <div className="flex items-center justify-between border-t border-hairline px-4 py-2 text-xs text-ink-muted">
        <span className="font-mono tabular-nums">
          {visible.length === 0
            ? "0 findings"
            : `${formatInt(page * PAGE + 1)} to ${formatInt(Math.min(visible.length, (page + 1) * PAGE))} of ${formatInt(visible.length)}`}
        </span>
        <div className="flex items-center gap-1">
          <PageButton disabled={page === 0} onClick={() => setPage(page - 1)} label="Previous page">
            <ChevronLeft className="h-3.5 w-3.5" strokeWidth={1.5} />
          </PageButton>
          <span className="px-1.5 font-mono tabular-nums">
            {page + 1} / {pages}
          </span>
          <PageButton disabled={page >= pages - 1} onClick={() => setPage(page + 1)} label="Next page">
            <ChevronRight className="h-3.5 w-3.5" strokeWidth={1.5} />
          </PageButton>
        </div>
      </div>
    </div>
  );
}

function Th({ children, className }: { children?: React.ReactNode; className?: string }) {
  return (
    <th className={cn("eyebrow border-b border-hairline px-3 py-2 font-medium", className)} scope="col">
      {children}
    </th>
  );
}

function Td({ children, className }: { children?: React.ReactNode; className?: string }) {
  return <td className={cn("border-b border-hairline px-3 py-2.5 align-middle", className)}>{children}</td>;
}

function PageButton({
  children,
  disabled,
  onClick,
  label,
}: {
  children: React.ReactNode;
  disabled: boolean;
  onClick: () => void;
  label: string;
}) {
  return (
    <button
      onClick={onClick}
      disabled={disabled}
      aria-label={label}
      className="flex h-6 w-6 items-center justify-center rounded-md border border-hairline bg-surface text-ink-secondary transition-colors hover:bg-slate-50 disabled:opacity-40"
    >
      {children}
    </button>
  );
}
