"use client";

import * as React from "react";

import { applyFilters, FindingsTable, type Filters } from "@/components/findings/findings-table";
import { Inspector } from "@/components/findings/inspector";
import { TelemetryRibbon } from "@/components/findings/telemetry-ribbon";
import { cellRef, formatInt, formatTimestamp } from "@/lib/utils";

import { useWorkspace } from "../workspace-context";
import { PageHeader } from "./page-header";

export function FindingsView() {
  const { run, selected, select } = useWorkspace();
  const [filters, setFilters] = React.useState<Filters>({ severity: "all", category: "all", showAccepted: false });

  const visible = React.useMemo(() => (run ? applyFilters(run.findings, filters) : []), [run, filters]);
  if (!run) return null;

  // Until a finding is picked, the inspector shows the worst one in view, so
  // the right pane is never empty on arrival. The URL is not touched for that.
  const first = visible[0];
  const shown = selected ?? (first ? cellRef(first.sheet, first.coordinate) : null);

  return (
    // Narrow screens stack the two panes, so the whole view scrolls. On a
    // desktop the view is fixed and each pane scrolls on its own, which keeps
    // the inspector beside the row you picked.
    <div className="scroll-thin flex h-full min-h-0 flex-col overflow-y-auto lg:overflow-hidden">
      <div className="space-y-4 px-5 pb-4 pt-5">
        <PageHeader
          title="Findings"
          description={`${formatInt(run.findings.length)} findings in ${run.file}, version ${run.version}, checked ${formatTimestamp(run.created_at)}. Worst first, one per cell.`}
        />
        <TelemetryRibbon run={run} />
      </div>

      <div className="flex flex-col gap-4 px-5 pb-5 lg:min-h-0 lg:flex-1 lg:flex-row">
        <section className="panel flex h-[32rem] min-w-0 flex-col overflow-hidden lg:h-auto lg:flex-[7]">
          <FindingsTable
            findings={run.findings}
            visible={visible}
            filters={filters}
            onFilters={setFilters}
            selected={shown}
            onSelect={select}
          />
        </section>
        <section className="panel flex min-h-[24rem] min-w-0 flex-col lg:min-h-0 lg:flex-[5] lg:overflow-hidden">
          <Inspector run={run} cellRefSelected={shown} />
        </section>
      </div>
    </div>
  );
}
