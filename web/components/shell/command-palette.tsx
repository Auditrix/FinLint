"use client";

import { ArrowRight, BookOpen, FileSpreadsheet, Upload } from "lucide-react";
import * as React from "react";

import {
  Command,
  CommandEmpty,
  CommandGroup,
  CommandInput,
  CommandItem,
  CommandList,
} from "@/components/ui/command";
import { Dialog, DialogContent, DialogTitle } from "@/components/ui/dialog";
import { SeverityPill } from "@/components/ui/pill";
import { ruleInfo } from "@/lib/rules";
import { cellRef } from "@/lib/utils";

import { useWorkspace, type View } from "../workspace-context";

const VIEW_LABELS: { view: View; label: string }[] = [
  { view: "findings", label: "Findings" },
  { view: "map", label: "Dependency map" },
  { view: "history", label: "Version history" },
  { view: "audit", label: "Audit log" },
  { view: "evaluation", label: "Evaluation" },
];

const MAX_MATCHES = 40;

export function CommandPalette() {
  const { paletteOpen, setPaletteOpen, run, files, select, setView, selectFile, setUploadOpen, mode, canUpload } = useWorkspace();
  const [query, setQuery] = React.useState("");

  React.useEffect(() => {
    if (!paletteOpen) setQuery("");
  }, [paletteOpen]);

  // Filtered by hand rather than by cmdk, because a workbook can have
  // thousands of findings and only the best few dozen are worth rendering.
  const matches = React.useMemo(() => {
    if (!run) return [];
    const q = query.trim().toLowerCase();
    const pool = run.findings;
    if (!q) return pool.slice(0, 8);
    return pool
      .filter((f) => {
        const ref = cellRef(f.sheet, f.coordinate).toLowerCase();
        return (
          ref.includes(q) ||
          f.coordinate.toLowerCase() === q ||
          f.rule_id.includes(q) ||
          ruleInfo(f.rule_id).label.toLowerCase().includes(q)
        );
      })
      .slice(0, MAX_MATCHES);
  }, [run, query]);

  function close() {
    setPaletteOpen(false);
  }

  return (
    <Dialog open={paletteOpen} onOpenChange={setPaletteOpen}>
      <DialogContent hideClose className="max-w-xl overflow-hidden p-0">
        <DialogTitle className="sr-only">Search</DialogTitle>
        <Command shouldFilter={false}>
          <CommandInput value={query} onValueChange={setQuery} placeholder="Search cells, rules or sheets" />
          <CommandList>
            <CommandEmpty>Nothing matches "{query}".</CommandEmpty>

            {matches.length > 0 && (
              <CommandGroup heading={query ? `Findings matching "${query}"` : "Worst findings"}>
                {matches.map((f) => {
                  const ref = cellRef(f.sheet, f.coordinate);
                  return (
                    <CommandItem
                      key={`${f.rule_id}|${ref}`}
                      value={`${f.rule_id}|${ref}`}
                      onSelect={() => {
                        setView("findings");
                        select(ref);
                        close();
                      }}
                    >
                      <SeverityPill severity={f.severity} className="w-[4.75rem] justify-start" />
                      <span className="font-mono text-xs text-ink">{ref}</span>
                      <span className="truncate text-ink-muted">{ruleInfo(f.rule_id).label}</span>
                    </CommandItem>
                  );
                })}
              </CommandGroup>
            )}

            {!query && (
              <>
                <CommandGroup heading="Go to">
                  {VIEW_LABELS.map((v) => (
                    <CommandItem
                      key={v.view}
                      value={`view ${v.label}`}
                      onSelect={() => {
                        setView(v.view);
                        close();
                      }}
                    >
                      <ArrowRight className="h-4 w-4 text-ink-muted" strokeWidth={1.5} />
                      {v.label}
                    </CommandItem>
                  ))}
                </CommandGroup>

                {files.length > 1 && (
                  <CommandGroup heading="Workbooks">
                    {files.map((file) => (
                      <CommandItem
                        key={file.name}
                        value={`file ${file.name}`}
                        onSelect={() => {
                          selectFile(file.name);
                          close();
                        }}
                      >
                        <FileSpreadsheet className="h-4 w-4 text-ink-muted" strokeWidth={1.5} />
                        {file.name}
                      </CommandItem>
                    ))}
                  </CommandGroup>
                )}

                <CommandGroup heading="Actions">
                  <CommandItem
                    value="action check"
                    disabled={mode !== "live" || !canUpload}
                    onSelect={() => {
                      setUploadOpen(true);
                      close();
                    }}
                  >
                    <Upload className="h-4 w-4 text-ink-muted" strokeWidth={1.5} />
                    Check a workbook
                    {mode !== "live" && <span className="ml-auto text-2xs text-ink-muted">needs the API</span>}
                    {mode === "live" && !canUpload && (
                      <span className="ml-auto text-2xs text-ink-muted">not for your role</span>
                    )}
                  </CommandItem>
                  <CommandItem value="action evaluation" onSelect={() => { setView("evaluation"); close(); }}>
                    <BookOpen className="h-4 w-4 text-ink-muted" strokeWidth={1.5} />
                    Read the evaluation results
                  </CommandItem>
                </CommandGroup>
              </>
            )}
          </CommandList>
        </Command>
      </DialogContent>
    </Dialog>
  );
}
