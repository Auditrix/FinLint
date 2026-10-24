"use client";

import { BookOpen, Check, ChevronDown, ChevronRight, FileSpreadsheet, Search, Upload } from "lucide-react";
import * as React from "react";

import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { Tip } from "@/components/ui/tooltip";
import { cn, formatTimestamp, shortSha } from "@/lib/utils";

import { useWorkspace } from "../workspace-context";
import { RulesDialog } from "./rules-dialog";

export function CommandHeader() {
  const { files, file, run, selectFile, setPaletteOpen, setUploadOpen, mode } = useWorkspace();
  const [rulesOpen, setRulesOpen] = React.useState(false);

  return (
    <header className="sticky top-0 z-30 flex h-14 shrink-0 items-center gap-3 border-b border-hairline bg-surface/95 px-5 backdrop-blur supports-[backdrop-filter]:bg-surface/80">
      {/* Breadcrumb and the workbook selector */}
      <div className="flex min-w-0 flex-1 items-center gap-1.5 text-[13px] md:flex-initial">
        <span className="hidden text-ink-muted md:inline">Workspace</span>
        <ChevronRight className="hidden h-3.5 w-3.5 text-slate-300 md:inline" strokeWidth={1.5} />
        <DropdownMenu>
          <DropdownMenuTrigger className="group flex min-w-0 items-center gap-1.5 rounded-md px-1.5 py-1 font-medium text-ink transition-colors hover:bg-slate-100">
            <FileSpreadsheet className="hidden h-4 w-4 shrink-0 text-ink-muted sm:block" strokeWidth={1.5} />
            <span className="min-w-[5rem] max-w-[18rem] truncate">{file ?? "No workbook"}</span>
            <ChevronDown className="h-3.5 w-3.5 shrink-0 text-ink-muted" strokeWidth={1.5} />
          </DropdownMenuTrigger>
          <DropdownMenuContent align="start" className="w-80">
            <DropdownMenuLabel>Checked workbooks</DropdownMenuLabel>
            {files.map((f) => (
              <DropdownMenuItem key={f.name} onSelect={() => selectFile(f.name)}>
                <FileSpreadsheet className="h-4 w-4 text-ink-muted" strokeWidth={1.5} />
                <div className="min-w-0 flex-1">
                  <div className="truncate text-ink">{f.name}</div>
                  <div className="font-mono text-2xs text-ink-muted">
                    v{f.latest_version} · score {f.latest_score} · {f.finding_count} findings
                  </div>
                </div>
                {f.name === file && <Check className="h-4 w-4 text-accent" strokeWidth={1.5} />}
              </DropdownMenuItem>
            ))}
            <DropdownMenuSeparator />
            <DropdownMenuItem onSelect={() => setUploadOpen(true)} disabled={mode !== "live"}>
              <Upload className="h-4 w-4" strokeWidth={1.5} />
              Check another workbook
            </DropdownMenuItem>
          </DropdownMenuContent>
        </DropdownMenu>

        {run && (
          <Tip content={`Checked ${formatTimestamp(run.created_at)}. SHA-256 of the exact bytes checked.`} side="bottom">
            <span className="hidden items-center gap-1.5 rounded-md border border-hairline bg-recessed px-2 py-0.5 font-mono text-2xs text-ink-secondary lg:inline-flex">
              <span className="text-ink">v{run.version}</span>
              <span className="text-slate-300">@</span>
              {shortSha(run.sha256)}
            </span>
          </Tip>
        )}
      </div>

      {/* Command palette trigger */}
      <button
        onClick={() => setPaletteOpen(true)}
        className="mx-auto hidden h-8 w-full max-w-md items-center gap-2 rounded-md border border-hairline bg-canvas px-2.5 text-[13px] text-ink-muted transition-colors hover:border-slate-300 hover:bg-surface md:flex"
      >
        <Search className="h-4 w-4" strokeWidth={1.5} />
        <span className="truncate">Search cells, rules or sheets</span>
        <kbd className="ml-auto rounded border border-hairline bg-surface px-1.5 py-0.5 font-mono text-2xs">Ctrl K</kbd>
      </button>

      <div className="ml-auto flex shrink-0 items-center gap-2 md:ml-0">
        <Button variant="secondary" onClick={() => setRulesOpen(true)}>
          <BookOpen className="h-4 w-4" strokeWidth={1.5} />
          <span className="hidden sm:inline">Rules</span>
        </Button>
        <Tip
          content={mode === "live" ? "Upload a workbook and run every check" : "Start the API to check a new workbook"}
          side="bottom"
        >
          <span>
            <Button variant="primary" onClick={() => setUploadOpen(true)} disabled={mode !== "live"}>
              <span
                className={cn(
                  "h-1.5 w-1.5 rounded-full",
                  mode === "live" ? "animate-pulse-dot bg-emerald-300" : "bg-white/50",
                )}
                aria-hidden
              />
              <span className="hidden sm:inline">Check workbook</span>
              <span className="sm:hidden">Check</span>
            </Button>
          </span>
        </Tip>
      </div>

      <RulesDialog open={rulesOpen} onOpenChange={setRulesOpen} />
    </header>
  );
}
