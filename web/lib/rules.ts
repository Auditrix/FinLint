import type { Severity } from "./types";

/**
 * The six checks in src/finlint/rules/checks.py, described for the person
 * reviewing them. The default severity matches what each check emits.
 *
 * "review" is what a human should actually look at. It is deliberately
 * phrased as a question, because FinLint flags; a person decides.
 */
export interface RuleInfo {
  id: string;
  label: string;
  category: "Structure" | "Calculation" | "Inputs";
  severity: Severity;
  summary: string;
  why: string;
  review: string;
}

export const RULES: Record<string, RuleInfo> = {
  circular_reference: {
    id: "circular_reference",
    label: "Circular reference",
    category: "Structure",
    severity: "critical",
    summary: "The cell depends on itself through a loop of formulas.",
    why: "A loop has no single correct answer. Excel either refuses it or iterates to whatever value it lands on, so every number downstream can change between recalculations.",
    review: "Is this loop intentional, with iterative calculation switched on deliberately, or did a reference point back at its own output?",
  },
  error_cells: {
    id: "error_cells",
    label: "Excel error value",
    category: "Calculation",
    severity: "high",
    summary: "The cell is showing one of Excel's own errors, such as #REF! or #DIV/0!.",
    why: "An error spreads. Every formula that reads this cell inherits it, so one broken input can blank out a whole statement.",
    review: "What does the formula read that is missing, zero, or the wrong type?",
  },
  formula_drift: {
    id: "formula_drift",
    label: "Inconsistent formula",
    category: "Calculation",
    severity: "high",
    summary: "This formula has a different shape from every other formula in its row.",
    why: "Forecast rows normally repeat one calculation across the periods. A single period computed differently is a classic copy and paste mistake.",
    review: "Compare this cell's shape with the rest of the row. Is the difference a deliberate one off, or a broken copy?",
  },
  hardcoded_value: {
    id: "hardcoded_value",
    label: "Hardcoded number",
    category: "Inputs",
    severity: "high",
    summary: "A typed number sits between formulas in a row that is otherwise calculated.",
    why: "A typed number does not update when its inputs change. It can be a mistake, or a constant locked in on purpose so nobody alters it, and only a person knows which.",
    review: "Was this number typed over a formula by accident, or deliberately locked? If deliberate, mark it as intentional with the reason.",
  },
  broken_link: {
    id: "broken_link",
    label: "Broken reference",
    category: "Structure",
    severity: "medium",
    summary: "A formula points at a sheet, a name or another workbook that is not there.",
    why: "The value Excel shows is whatever it last remembered. Open the file anywhere else and the number may be stale or replaced by an error.",
    review: "Was the sheet renamed or deleted, or does this read from a file that should be bundled with this one?",
  },
  dead_input: {
    id: "dead_input",
    label: "Unused input",
    category: "Inputs",
    severity: "low",
    summary: "A typed number that no formula reads, so changing it changes nothing.",
    why: "Someone may believe this drives the model when it does not. Often harmless, such as a note or a label, which is why it is only a warning.",
    review: "Should this input feed a calculation, or is it a note that can be left alone?",
  },
};

export function ruleInfo(id: string): RuleInfo {
  return (
    RULES[id] ?? {
      id,
      label: id.replace(/_/g, " "),
      category: "Calculation",
      severity: "medium",
      summary: "A spreadsheet check found an issue.",
      why: "",
      review: "",
    }
  );
}

export const CATEGORIES = ["Structure", "Calculation", "Inputs"] as const;

/**
 * Severity tokens. The pattern is the same for all four, so a pill always
 * reads the same way: soft background, hairline border, strong text, a dot.
 */
export const SEVERITY_STYLE: Record<
  Severity,
  { label: string; pill: string; dot: string; bar: string; text: string }
> = {
  critical: {
    label: "Critical",
    pill: "bg-red-50 border-red-200 text-red-600",
    dot: "bg-red-500",
    bar: "bg-red-500",
    text: "text-red-600",
  },
  high: {
    label: "High",
    pill: "bg-orange-50 border-orange-200 text-orange-600",
    dot: "bg-orange-500",
    bar: "bg-orange-500",
    text: "text-orange-600",
  },
  medium: {
    label: "Medium",
    pill: "bg-amber-50 border-amber-200 text-amber-600",
    dot: "bg-amber-500",
    bar: "bg-amber-400",
    text: "text-amber-600",
  },
  low: {
    label: "Low",
    pill: "bg-slate-50 border-slate-200 text-slate-600",
    dot: "bg-slate-400",
    bar: "bg-slate-300",
    text: "text-slate-600",
  },
};

/** The verdict sentence for a risk score, matching rules/score.py's bands. */
export function scoreBand(score: number): { label: string; severity: Severity | "clean" } {
  if (score === 0) return { label: "No findings", severity: "clean" };
  if (score >= 80) return { label: "Critical band", severity: "critical" };
  if (score >= 60) return { label: "High band", severity: "high" };
  if (score >= 40) return { label: "Medium band", severity: "medium" };
  return { label: "Low band", severity: "low" };
}
