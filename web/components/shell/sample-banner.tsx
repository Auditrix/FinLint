"use client";

import { Info } from "lucide-react";

import { useWorkspace } from "../workspace-context";

/**
 * Shown whenever the session is reading saved data instead of the API, so a
 * saved run is never mistaken for a live check.
 */
export function SampleBanner() {
  const { mode, run } = useWorkspace();
  if (mode !== "sample") return null;

  return (
    <div className="flex items-center gap-2.5 border-b border-sky-200 bg-sky-50 px-5 py-2 text-xs text-sky-800">
      <Info className="h-3.5 w-3.5 shrink-0 text-sky-600" strokeWidth={1.5} />
      <span>
        <span className="font-medium">Saved sample.</span> A real run of the real engine
        {run ? (
          <>
            {" "}
            on <span className="font-mono">{run.file}</span>
          </>
        ) : null}
        , exported by <span className="font-mono">scripts/export_ui_fixture.py</span>. Start the API on port 8000 to
        check new workbooks.
      </span>
    </div>
  );
}
