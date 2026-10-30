"use client";

import { motion } from "framer-motion";
import {
  ChevronsLeft,
  ChevronsRight,
  FlaskConical,
  History,
  ListChecks,
  LogOut,
  Network,
  ScrollText,
} from "lucide-react";
import * as React from "react";

import { Tip } from "@/components/ui/tooltip";
import { cn } from "@/lib/utils";

import { useWorkspace, type View } from "../workspace-context";
import { BrandMark } from "./brand-mark";

const SECTIONS: { title: string; items: { view: View; label: string; icon: typeof ListChecks; hint: string }[] }[] = [
  {
    title: "Review",
    items: [
      { view: "findings", label: "Findings", icon: ListChecks, hint: "Every problem, worst first" },
      { view: "map", label: "Dependency map", icon: Network, hint: "What feeds what" },
    ],
  },
  {
    title: "Record",
    items: [
      { view: "history", label: "Version history", icon: History, hint: "What changed between checks" },
      { view: "audit", label: "Audit log", icon: ScrollText, hint: "Who accepted what, and why" },
    ],
  },
  {
    title: "Results",
    items: [{ view: "evaluation", label: "Evaluation", icon: FlaskConical, hint: "How well FinLint performs" }],
  },
];

const SPRING = { type: "spring", stiffness: 400, damping: 30 } as const;

export function NavRail() {
  const { view, setView, mode, health, run, account, signOut } = useWorkspace();
  const [collapsed, setCollapsed] = React.useState(false);

  // Narrow windows start collapsed so the rail never takes half the screen.
  // Only on first load: once someone clicks the toggle, their choice stands.
  React.useEffect(() => {
    if (window.matchMedia("(max-width: 1023px)").matches) setCollapsed(true);
  }, []);

  const counts: Partial<Record<View, number>> = {
    findings: run ? run.findings.filter((f) => !f.approved).length : undefined,
    audit: run ? run.findings.filter((f) => f.approved).length : undefined,
  };

  return (
    // A plain inline width with a CSS transition, not a framer animation. The
    // rail sets the width of the whole layout, so it has to be right on the
    // very first paint; framer was leaving it unset and the rail shrank to
    // whatever its labels needed.
    <aside
      style={{ width: collapsed ? 56 : 240 }}
      className="relative flex h-full shrink-0 flex-col border-r border-hairline bg-surface transition-[width] duration-200 ease-out motion-reduce:transition-none"
    >
      <div className="flex h-14 items-center gap-2.5 border-b border-hairline px-4">
        <BrandMark className="h-5 w-5 shrink-0" />
        {!collapsed && (
          <div className="flex min-w-0 items-baseline gap-1.5">
            <span className="font-display text-[15px] font-bold tracking-tight text-ink">FinLint</span>
            <span className="truncate font-mono text-2xs text-ink-muted">v{health?.version ?? "0.1.0"}</span>
          </div>
        )}
      </div>

      <nav className="scroll-thin flex-1 overflow-y-auto px-2 py-3">
        {SECTIONS.map((section) => (
          <div key={section.title} className="mb-4">
            {!collapsed && <div className="eyebrow px-2 pb-1.5">{section.title}</div>}
            <ul className="space-y-0.5">
              {section.items.map((item) => {
                const active = view === item.view;
                const Icon = item.icon;
                const count = counts[item.view];
                const button = (
                  <button
                    onClick={() => setView(item.view)}
                    // Named explicitly: when collapsed the visible label is gone,
                    // and a tooltip is a description, not a name.
                    aria-label={item.label}
                    className={cn(
                      "relative flex h-8 w-full items-center gap-2.5 rounded-md px-2 text-[13px] transition-colors",
                      active ? "text-ink" : "text-ink-secondary hover:bg-slate-50 hover:text-ink",
                    )}
                    aria-current={active ? "page" : undefined}
                  >
                    {active && (
                      <motion.span
                        layoutId="nav-active"
                        transition={SPRING}
                        className="absolute inset-0 rounded-md border border-hairline bg-recessed"
                      />
                    )}
                    <Icon className="relative h-4 w-4 shrink-0" strokeWidth={1.5} />
                    {!collapsed && (
                      <>
                        <span className="relative truncate font-medium">{item.label}</span>
                        {count !== undefined && (
                          <span className="relative ml-auto font-mono text-2xs text-ink-muted">{count}</span>
                        )}
                      </>
                    )}
                  </button>
                );
                return (
                  <li key={item.view}>
                    {collapsed ? (
                      <Tip content={item.label} side="right">
                        {button}
                      </Tip>
                    ) : (
                      button
                    )}
                  </li>
                );
              })}
            </ul>
          </div>
        ))}
      </nav>

      <div className="border-t border-hairline p-2">
        {account && (
          <div className={cn("mb-2 flex items-center gap-2", collapsed ? "justify-center" : "px-1")}>
            {!collapsed && (
              <div className="min-w-0 flex-1">
                <div className="truncate text-[13px] font-medium text-ink">{account.username}</div>
                <div className="text-2xs capitalize text-ink-muted">{account.role}</div>
              </div>
            )}
            <Tip content="Sign out" side={collapsed ? "right" : "top"}>
              <button
                onClick={() => void signOut()}
                aria-label="Sign out"
                className="flex h-7 w-7 shrink-0 items-center justify-center rounded-md text-ink-muted transition-colors hover:bg-slate-100 hover:text-ink"
              >
                <LogOut className="h-4 w-4" strokeWidth={1.5} />
              </button>
            </Tip>
          </div>
        )}
        {!collapsed && (
          <div className="mb-2 space-y-1.5 rounded-md border border-hairline bg-canvas px-2.5 py-2">
            {/* A saved sample has no live database or model behind it, whatever
                its saved health file says, so everything reads off but the data. */}
            <StatusRow label="Live API" on={mode === "live"} />
            <StatusRow label="Run history" on={mode === "live" && Boolean(health?.database)} />
            <StatusRow label="Standards agent" on={mode === "live" && Boolean(health?.llm)} />
          </div>
        )}
        <button
          onClick={() => setCollapsed((c) => !c)}
          className="flex h-7 w-full items-center justify-center gap-2 rounded-md text-xs text-ink-muted transition-colors hover:bg-slate-50 hover:text-ink"
          aria-label={collapsed ? "Expand navigation" : "Collapse navigation"}
        >
          {collapsed ? (
            <ChevronsRight className="h-4 w-4" strokeWidth={1.5} />
          ) : (
            <>
              <ChevronsLeft className="h-4 w-4" strokeWidth={1.5} />
              Collapse
            </>
          )}
        </button>
      </div>
    </aside>
  );
}

function StatusRow({ label, on }: { label: string; on: boolean }) {
  return (
    <div className="flex items-center gap-2 text-2xs text-ink-secondary">
      <span className={cn("h-1.5 w-1.5 rounded-full", on ? "bg-emerald-500" : "bg-slate-300")} aria-hidden />
      <span className="truncate">{label}</span>
      <span className="ml-auto font-mono text-ink-muted">{on ? "on" : "off"}</span>
    </div>
  );
}
