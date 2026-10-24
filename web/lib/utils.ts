import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";

import type { CellValue, Finding } from "./types";

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

const integer = new Intl.NumberFormat("en-US");

export function formatInt(n: number): string {
  return integer.format(n);
}

export function formatPercent(n: number, digits = 1): string {
  return `${(n * 100).toFixed(digits)}%`;
}

/** The same "Sheet!A1" reference the backend builds with make_ref. */
export function cellRef(sheet: string, coordinate: string): string {
  return `${sheet}!${coordinate}`;
}

/** Split on the LAST "!", because a sheet name may itself contain one. */
export function splitRef(ref: string): { sheet: string; coordinate: string } {
  const at = ref.lastIndexOf("!");
  if (at === -1) return { sheet: "", coordinate: ref };
  return { sheet: ref.slice(0, at), coordinate: ref.slice(at + 1) };
}

/**
 * The same identity lineage/diff.py uses: rule, sheet and cell. Kept here so
 * the frontend never invents its own idea of "the same finding".
 */
export function findingKey(f: Pick<Finding, "rule_id" | "sheet" | "coordinate">): string {
  return `${f.rule_id}|${f.sheet}|${f.coordinate}`;
}

export function shortSha(sha: string): string {
  return sha.slice(0, 12);
}

/** UTC from the API, shown in the viewer's own local time. */
export function formatTimestamp(iso: string): string {
  const d = new Date(iso);
  return d.toLocaleString(undefined, {
    year: "numeric",
    month: "short",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  });
}

export function formatValue(value: CellValue): string {
  if (value === null) return "empty";
  if (typeof value === "number") {
    return Number.isInteger(value)
      ? formatInt(value)
      : value.toLocaleString("en-US", { maximumFractionDigits: 6 });
  }
  if (typeof value === "boolean") return value ? "TRUE" : "FALSE";
  return value;
}
