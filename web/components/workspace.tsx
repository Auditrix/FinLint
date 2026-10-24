"use client";

import { AnimatePresence, MotionConfig, motion } from "framer-motion";
import { AlertCircle, Loader2 } from "lucide-react";

import { TooltipProvider } from "@/components/ui/tooltip";

import { AuditView } from "./views/audit-view";
import { DependencyView } from "./views/dependency-view";
import { EvaluationView } from "./views/evaluation-view";
import { FindingsView } from "./views/findings-view";
import { HistoryView } from "./views/history-view";
import { CommandHeader } from "./shell/command-header";
import { CommandPalette } from "./shell/command-palette";
import { NavRail } from "./shell/nav-rail";
import { SampleBanner } from "./shell/sample-banner";
import { UploadDialog } from "./shell/upload-dialog";
import { useWorkspace, WorkspaceProvider } from "./workspace-context";

export function Workspace() {
  return (
    <WorkspaceProvider>
      {/* framer-motion ignores the system "reduce motion" setting unless told
          to follow it. With "user" it drops movement and keeps simple fades. */}
      <MotionConfig reducedMotion="user">
        <TooltipProvider>
          <div className="flex h-screen overflow-hidden">
            <NavRail />
            <div className="flex min-w-0 flex-1 flex-col">
              <CommandHeader />
              <SampleBanner />
              <main className="min-h-0 flex-1">
                <ViewSwitch />
              </main>
            </div>
          </div>
          <CommandPalette />
          <UploadDialog />
        </TooltipProvider>
      </MotionConfig>
    </WorkspaceProvider>
  );
}

function ViewSwitch() {
  const { view, loading, error, run } = useWorkspace();

  // The evaluation page needs no workbook, so it renders even with none loaded.
  if (view !== "evaluation") {
    if (error && !run) return <Centered tone="error">{error}</Centered>;
    if (loading && !run) {
      return (
        <Centered>
          <Loader2 className="h-4 w-4 animate-spin text-accent" strokeWidth={1.5} />
          Loading the latest check
        </Centered>
      );
    }
    if (!run) return <Centered>No workbook has been checked yet. Use Check workbook to start.</Centered>;
  }

  return (
    <AnimatePresence mode="wait" initial={false}>
      <motion.div
        key={view}
        initial={{ opacity: 0, y: 4 }}
        animate={{ opacity: 1, y: 0 }}
        exit={{ opacity: 0, y: -2 }}
        transition={{ type: "spring", stiffness: 400, damping: 30 }}
        className="h-full"
      >
        {view === "findings" && <FindingsView />}
        {view === "map" && <DependencyView />}
        {view === "history" && <HistoryView />}
        {view === "audit" && <AuditView />}
        {view === "evaluation" && <EvaluationView />}
      </motion.div>
    </AnimatePresence>
  );
}

function Centered({ children, tone }: { children: React.ReactNode; tone?: "error" }) {
  return (
    <div className="flex h-full items-center justify-center p-8">
      <div
        className={
          tone === "error"
            ? "flex max-w-md items-start gap-2 rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-[13px] text-red-700"
            : "flex items-center gap-2 text-[13px] text-ink-muted"
        }
      >
        {tone === "error" && <AlertCircle className="mt-0.5 h-4 w-4 shrink-0" strokeWidth={1.5} />}
        {children}
      </div>
    </div>
  );
}
