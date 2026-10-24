"use client";

import { AlertCircle, CheckCircle2, Loader2, Lock, UserCheck } from "lucide-react";
import * as React from "react";

import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import * as api from "@/lib/api";
import { ruleInfo } from "@/lib/rules";
import type { AnnotatedFinding } from "@/lib/types";
import { cellRef } from "@/lib/utils";

import { useWorkspace } from "../workspace-context";

const NAME_KEY = "finlint.reviewer";

/**
 * The human decision, in place of a "fix" button.
 *
 * FinLint never changes the workbook. A hardcoded number can be a mistake or a
 * constant locked in on purpose, and only a person knows which. So the only
 * action here records a decision and its reason, permanently, against this
 * file. The cell is never touched.
 */
export function Decision({ file, finding }: { file: string; finding: AnnotatedFinding }) {
  const { refresh, mode, setView } = useWorkspace();
  const [open, setOpen] = React.useState(false);
  const [reason, setReason] = React.useState("");
  const [who, setWho] = React.useState("");
  const [busy, setBusy] = React.useState(false);
  const [error, setError] = React.useState<string | null>(null);
  // Set the moment the decision is stored, whether or not the screen manages
  // to refresh afterwards. See submit().
  const [saved, setSaved] = React.useState(false);

  const key = `${finding.rule_id}|${finding.sheet}|${finding.coordinate}`;
  React.useEffect(() => setSaved(false), [key]);

  React.useEffect(() => {
    try {
      setWho(window.localStorage.getItem(NAME_KEY) ?? "");
    } catch {
      /* storage may be blocked; the field just starts empty */
    }
  }, []);

  React.useEffect(() => {
    if (!open) {
      setReason("");
      setError(null);
    }
  }, [open]);

  if (finding.approved || saved) {
    return (
      <div className="flex items-start gap-2.5 rounded-md border border-emerald-200 bg-emerald-50 px-3 py-3">
        <CheckCircle2 className="mt-0.5 h-4 w-4 shrink-0 text-emerald-600" strokeWidth={1.5} />
        <div className="text-[13px]">
          <div className="font-medium text-emerald-800">Accepted as intentional</div>
          <p className="mt-0.5 text-xs text-emerald-700">
            A person recorded why this is deliberate. It stays accepted on every future version of this file.{" "}
            <button onClick={() => setView("audit")} className="font-medium underline underline-offset-2">
              See the audit log
            </button>
          </p>
        </div>
      </div>
    );
  }

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await api.approveFinding(file, finding, reason, who);
    } catch (err) {
      // Nothing was stored, so trying again is safe.
      setError(err instanceof Error ? err.message : "The decision was not saved.");
      setBusy(false);
      return;
    }

    // Stored. From here on nothing may offer a retry: approvals are an audit
    // trail and are appended, never replaced, so a second click would record a
    // second decision. A failed refresh below used to keep the dialog open with
    // the reason filled in, inviting exactly that.
    setSaved(true);
    setOpen(false);
    setBusy(false);
    try {
      window.localStorage.setItem(NAME_KEY, who.trim());
    } catch {
      /* not essential */
    }
    try {
      await refresh();
    } catch {
      /* the decision is stored; the list catches up on the next load */
    }
  }

  return (
    <>
      <div className="space-y-2.5">
        <div className="flex items-start gap-2 text-[13px] text-ink-secondary">
          <Lock className="mt-0.5 h-3.5 w-3.5 shrink-0 text-ink-muted" strokeWidth={1.5} />
          <span>
            FinLint does not change your workbook. If this is deliberate, record why, and it will stay accepted on every
            future version.
          </span>
        </div>
        <Button onClick={() => setOpen(true)}>
          <UserCheck className="h-4 w-4" strokeWidth={1.5} />
          Mark as intentional
        </Button>
      </div>

      <Dialog open={open} onOpenChange={(o) => !busy && setOpen(o)}>
        <DialogContent>
          <form onSubmit={submit}>
            <DialogHeader>
              <DialogTitle>Mark as intentional</DialogTitle>
              <DialogDescription>
                {ruleInfo(finding.rule_id).label} at{" "}
                <span className="font-mono text-ink">{cellRef(finding.sheet, finding.coordinate)}</span>. This records a
                decision. The cell itself is not changed.
              </DialogDescription>
            </DialogHeader>
            <div className="space-y-3.5 px-5 py-4">
              <label className="block">
                <span className="mb-1 block text-xs font-medium text-ink">Why is this deliberate?</span>
                <textarea
                  value={reason}
                  onChange={(e) => setReason(e.target.value)}
                  rows={3}
                  autoFocus
                  placeholder="For example: the tax rate is locked by policy so nobody can change it"
                  className="w-full resize-none rounded-md border border-hairline bg-surface px-3 py-2 text-[13px] text-ink placeholder:text-ink-muted focus:border-accent"
                />
              </label>
              <label className="block">
                <span className="mb-1 block text-xs font-medium text-ink">Decided by</span>
                <input
                  value={who}
                  onChange={(e) => setWho(e.target.value)}
                  placeholder="Your name"
                  className="h-8 w-full rounded-md border border-hairline bg-surface px-3 text-[13px] text-ink placeholder:text-ink-muted focus:border-accent"
                />
              </label>
              {mode === "sample" && (
                <p className="text-xs text-ink-muted">
                  Saved sample: this decision lasts only until you reload the page, and is not written to the run history.
                </p>
              )}
              {error && (
                <div className="flex items-start gap-2 rounded-md border border-red-200 bg-red-50 px-3 py-2.5 text-xs text-red-700">
                  <AlertCircle className="mt-0.5 h-3.5 w-3.5 shrink-0" strokeWidth={1.5} />
                  {error}
                </div>
              )}
            </div>
            <div className="flex justify-end gap-2 border-t border-hairline px-5 py-3">
              <Button type="button" variant="ghost" onClick={() => setOpen(false)} disabled={busy}>
                Cancel
              </Button>
              <Button type="submit" variant="primary" disabled={busy || !reason.trim() || !who.trim()}>
                {busy && <Loader2 className="h-4 w-4 animate-spin" strokeWidth={1.5} />}
                Record decision
              </Button>
            </div>
          </form>
        </DialogContent>
      </Dialog>
    </>
  );
}
