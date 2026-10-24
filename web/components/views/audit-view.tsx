"use client";

import { AlertCircle, Loader2, ScrollText, ShieldCheck } from "lucide-react";
import * as React from "react";

import { Tag } from "@/components/ui/pill";
import * as api from "@/lib/api";
import { ruleInfo } from "@/lib/rules";
import type { Approval } from "@/lib/types";
import { cellRef, formatTimestamp } from "@/lib/utils";

import { useWorkspace } from "../workspace-context";
import { PageHeader } from "./page-header";

/**
 * Every human decision on this file, newest first, including two decisions on
 * one cell. This is the record the signer needs: who accepted what, when, and
 * the reason they gave.
 */
export function AuditView() {
  const { run, mode, setView, select } = useWorkspace();
  const [rows, setRows] = React.useState<Approval[] | null>(null);
  const [error, setError] = React.useState<string | null>(null);

  React.useEffect(() => {
    if (!run) return;
    let cancelled = false;
    // Cleared first, so the previous workbook's decisions never sit under the
    // next workbook's name while it loads.
    setRows(null);
    setError(null);
    api
      .getApprovals(run.file)
      .then((r) => !cancelled && setRows(r))
      .catch((e) => {
        // A failed load is reported as a failure. Showing "No decisions yet"
        // here would tell the person signing off that nothing was ever
        // accepted, which on an audit trail is a false statement.
        if (!cancelled) setError(e instanceof Error ? e.message : "The decisions could not be loaded.");
      });
    return () => {
      cancelled = true;
    };
  }, [run]);

  if (!run) return null;

  return (
    <div className="scroll-thin h-full overflow-y-auto">
      <div className="space-y-4 p-5">
        <PageHeader
          title="Audit log"
          description={`Decisions people made about ${run.file}. FinLint flags; a person decides, and the decision is kept.`}
        />

        <div className="grid grid-cols-1 gap-4 xl:grid-cols-[1fr_22rem]">
          <section className="panel overflow-hidden">
            <div className="flex items-center justify-between border-b border-hairline px-4 py-3">
              <span className="eyebrow">Decisions</span>
              {rows && <span className="font-mono text-2xs text-ink-muted">{rows.length}</span>}
            </div>

            {error ? (
              <div className="m-4 flex items-start gap-2 rounded-md border border-red-200 bg-red-50 px-3 py-2.5 text-xs text-red-700">
                <AlertCircle className="mt-0.5 h-3.5 w-3.5 shrink-0" strokeWidth={1.5} />
                <span>
                  <span className="font-medium">The decisions could not be loaded.</span> This does not mean there are
                  none. {error}
                </span>
              </div>
            ) : rows === null ? (
              <div className="flex items-center gap-2 px-4 py-10 text-xs text-ink-muted">
                <Loader2 className="h-3.5 w-3.5 animate-spin text-accent" strokeWidth={1.5} />
                Loading decisions
              </div>
            ) : rows.length === 0 ? (
              <div className="flex flex-col items-center gap-2 px-6 py-14 text-center">
                <ScrollText className="h-5 w-5 text-slate-300" strokeWidth={1.5} />
                <div className="font-medium text-ink">No decisions yet</div>
                <p className="max-w-sm text-xs text-ink-muted">
                  When a reviewer marks a finding as intentional, it appears here with their name and reason, and stays
                  accepted on every later version of the file.
                </p>
                <button
                  onClick={() => setView("findings")}
                  className="mt-1 text-xs font-medium text-accent hover:underline"
                >
                  Review the findings
                </button>
              </div>
            ) : (
              <div className="scroll-thin overflow-x-auto">
                <table className="w-full border-separate border-spacing-0 text-left">
                  <thead>
                    <tr className="bg-recessed">
                      {["Decided", "By", "Cell", "Check", "Reason"].map((h) => (
                        <th key={h} className="eyebrow border-b border-hairline px-4 py-2 font-medium">
                          {h}
                        </th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {rows.map((a, i) => {
                      const ref = cellRef(a.sheet, a.coordinate);
                      return (
                        <tr key={`${ref}|${a.decided_at}|${i}`} className="align-top hover:bg-slate-50/80">
                          <td className="whitespace-nowrap border-b border-hairline px-4 py-2.5 text-xs text-ink-secondary">
                            {formatTimestamp(a.decided_at)}
                          </td>
                          <td className="whitespace-nowrap border-b border-hairline px-4 py-2.5 text-[13px] font-medium text-ink">
                            {a.decided_by}
                          </td>
                          <td className="whitespace-nowrap border-b border-hairline px-4 py-2.5">
                            <button
                              onClick={() => {
                                setView("findings");
                                select(ref);
                              }}
                              className="font-mono text-xs text-accent hover:underline"
                            >
                              {ref}
                            </button>
                          </td>
                          <td className="whitespace-nowrap border-b border-hairline px-4 py-2.5 text-xs text-ink-secondary">
                            {ruleInfo(a.rule_id).label}
                          </td>
                          <td className="border-b border-hairline px-4 py-2.5 text-[13px] text-ink">{a.reason}</td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            )}
          </section>

          <aside className="panel space-y-3 p-4">
            <div className="flex items-center gap-2">
              <ShieldCheck className="h-4 w-4 text-ink-muted" strokeWidth={1.5} />
              <span className="eyebrow">Why decisions, not fixes</span>
            </div>
            <p className="text-[13px] leading-relaxed text-ink-secondary">
              The same hardcoded number can be a mistake or a control locked in on purpose. The tool sees the formula;
              only a person knows the intent.
            </p>
            <p className="text-[13px] leading-relaxed text-ink-secondary">
              Whoever fixes work should not also be the one who judges it. So FinLint never edits the workbook. It
              records who accepted each finding and why, so the check can be proven afterwards.
            </p>
            <div className="flex flex-wrap gap-1.5 pt-1">
              <Tag mono={false}>Read only</Tag>
              <Tag mono={false}>Reason required</Tag>
              <Tag mono={false}>Kept across versions</Tag>
            </div>
            {mode === "sample" && (
              <p className="border-t border-hairline pt-3 text-xs text-ink-muted">
                Saved sample: decisions made here last only until you reload the page, and are not written to the run history.
              </p>
            )}
          </aside>
        </div>
      </div>
    </div>
  );
}
