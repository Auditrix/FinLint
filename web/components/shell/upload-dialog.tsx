"use client";

import { AlertCircle, FileSpreadsheet, Loader2, Lock, UploadCloud } from "lucide-react";
import * as React from "react";

import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import * as api from "@/lib/api";
import { cn, formatInt } from "@/lib/utils";

import { useWorkspace } from "../workspace-context";

const ACCEPTED = [".xlsx", ".xlsm"];

// What happens during the one request, in order. Listed so the wait means
// something, not animated as if each step reported its own progress.
const STEPS = [
  "Reading every formula and stored value",
  "Mapping what feeds what",
  "Running the six checks",
  "Saving this as a new version",
];

export function UploadDialog() {
  const { uploadOpen, setUploadOpen, adoptRun } = useWorkspace();
  const [file, setFile] = React.useState<File | null>(null);
  const [dragging, setDragging] = React.useState(false);
  const [busy, setBusy] = React.useState(false);
  const [error, setError] = React.useState<string | null>(null);
  // The version number once the server has stored the check. After that,
  // running it again would store a duplicate version, so it is not offered.
  const [savedVersion, setSavedVersion] = React.useState<number | null>(null);
  const input = React.useRef<HTMLInputElement>(null);

  React.useEffect(() => {
    if (!uploadOpen) {
      setFile(null);
      setError(null);
      setBusy(false);
      setSavedVersion(null);
    }
  }, [uploadOpen]);

  function pick(candidate: File | undefined) {
    if (!candidate) return;
    const ok = ACCEPTED.some((ext) => candidate.name.toLowerCase().endsWith(ext));
    if (!ok) {
      setError(`${candidate.name} is not an Excel workbook. FinLint reads .xlsx and .xlsm files.`);
      setFile(null);
      return;
    }
    setError(null);
    setFile(candidate);
  }

  async function run() {
    if (!file) return;
    setBusy(true);
    setError(null);

    let result;
    try {
      result = await api.checkWorkbook(file);
    } catch (e) {
      // Nothing was stored, so trying again is safe.
      setError(e instanceof Error ? e.message : "The check did not finish.");
      setBusy(false);
      return;
    }

    // Stored as a new version. A failure from here on is only the screen
    // failing to refresh, and must not invite a second upload.
    setSavedVersion(result.version);
    try {
      await adoptRun(result);
      setUploadOpen(false);
    } catch {
      setError(
        `Checked and saved as version ${result.version}, but the screen could not refresh. Close this and reload the page to see it.`,
      );
      setBusy(false);
    }
  }

  return (
    <Dialog open={uploadOpen} onOpenChange={(open) => !busy && setUploadOpen(open)}>
      <DialogContent hideClose={busy}>
        <DialogHeader>
          <DialogTitle>Check a workbook</DialogTitle>
          <DialogDescription>
            Every check is deterministic code, so the same file always gets the same findings and the same score.
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-4 px-5 py-4">
          {/* Kept outside the drop zone: an input nested in a button is invalid
              HTML, and some browsers send the click to the wrong one. */}
          <input
            ref={input}
            type="file"
            accept={ACCEPTED.join(",")}
            className="hidden"
            aria-label="Choose a workbook"
            onChange={(e) => pick(e.target.files?.[0])}
          />
          {!busy ? (
            <button
              type="button"
              onClick={() => input.current?.click()}
              onDragOver={(e) => {
                e.preventDefault();
                setDragging(true);
              }}
              onDragLeave={() => setDragging(false)}
              onDrop={(e) => {
                e.preventDefault();
                setDragging(false);
                pick(e.dataTransfer.files[0]);
              }}
              className={cn(
                "flex w-full flex-col items-center gap-2 rounded-lg border border-dashed px-6 py-8 text-center transition-colors",
                dragging ? "border-accent bg-accent-soft" : "border-slate-300 bg-canvas hover:border-slate-400",
              )}
            >
              {file ? (
                <>
                  <FileSpreadsheet className="h-6 w-6 text-accent" strokeWidth={1.5} />
                  <span className="font-medium text-ink">{file.name}</span>
                  <span className="font-mono text-2xs text-ink-muted">{formatInt(Math.round(file.size / 1024))} KB</span>
                </>
              ) : (
                <>
                  <UploadCloud className="h-6 w-6 text-ink-muted" strokeWidth={1.5} />
                  <span className="font-medium text-ink">Drop a workbook here, or choose one</span>
                  <span className="text-xs text-ink-muted">.xlsx or .xlsm</span>
                </>
              )}
            </button>
          ) : (
            <ol className="space-y-2 rounded-lg border border-hairline bg-canvas p-4">
              {STEPS.map((step) => (
                <li key={step} className="flex items-center gap-2.5 text-[13px] text-ink-secondary">
                  <Loader2 className="h-3.5 w-3.5 animate-spin text-accent" strokeWidth={1.5} />
                  {step}
                </li>
              ))}
            </ol>
          )}

          <div className="flex items-start gap-2 rounded-md border border-hairline bg-surface px-3 py-2.5 text-xs text-ink-secondary">
            <Lock className="mt-0.5 h-3.5 w-3.5 shrink-0 text-ink-muted" strokeWidth={1.5} />
            FinLint only reads. Your workbook is never changed, and every decision stays with a person.
          </div>

          {error && (
            <div className="flex items-start gap-2 rounded-md border border-red-200 bg-red-50 px-3 py-2.5 text-xs text-red-700">
              <AlertCircle className="mt-0.5 h-3.5 w-3.5 shrink-0" strokeWidth={1.5} />
              {error}
            </div>
          )}
        </div>

        <div className="flex justify-end gap-2 border-t border-hairline px-5 py-3">
          <Button variant="ghost" onClick={() => setUploadOpen(false)} disabled={busy}>
            {savedVersion !== null ? "Close" : "Cancel"}
          </Button>
          <Button variant="primary" onClick={run} disabled={!file || busy || savedVersion !== null}>
            {busy && <Loader2 className="h-4 w-4 animate-spin" strokeWidth={1.5} />}
            {busy ? "Checking" : "Run checks"}
          </Button>
        </div>
      </DialogContent>
    </Dialog>
  );
}
