import * as React from "react";

import { SEVERITY_STYLE } from "@/lib/rules";
import type { Severity } from "@/lib/types";
import { cn } from "@/lib/utils";

const BASE = "inline-flex items-center gap-1.5 rounded-md border px-2 py-0.5 font-mono text-xs font-medium";

/** A severity badge. The pattern is identical for all four levels. */
export function SeverityPill({ severity, className }: { severity: Severity; className?: string }) {
  const style = SEVERITY_STYLE[severity];
  return (
    <span className={cn(BASE, style.pill, className)}>
      <span className={cn("h-1.5 w-1.5 rounded-full", style.dot)} aria-hidden />
      {style.label}
    </span>
  );
}

type Tone = "neutral" | "accent" | "verified" | "info" | "new";

const TONE: Record<Tone, string> = {
  neutral: "bg-slate-50 border-slate-200 text-slate-600",
  accent: "bg-accent-soft border-indigo-200 text-accent",
  verified: "bg-emerald-50 border-emerald-200 text-emerald-600",
  info: "bg-sky-50 border-sky-200 text-sky-600",
  new: "bg-indigo-50 border-indigo-200 text-indigo-600",
};

/** A non severity tag: rule ids, sheet names, statuses. */
export function Tag({
  tone = "neutral",
  mono = true,
  className,
  children,
  icon,
}: {
  tone?: Tone;
  mono?: boolean;
  className?: string;
  children: React.ReactNode;
  icon?: React.ReactNode;
}) {
  return (
    <span className={cn(BASE, !mono && "font-sans", TONE[tone], className)}>
      {icon}
      {children}
    </span>
  );
}
