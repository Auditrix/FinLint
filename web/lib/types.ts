/**
 * The TypeScript mirror of docs/api_contract.md.
 *
 * If this file and the contract ever disagree, the contract wins and this file
 * is wrong. Every shape here maps one to one onto a Python model in the
 * backend, named in each comment.
 */

/** rules.model.Severity, worst first. */
export type Severity = "critical" | "high" | "medium" | "low";

export const SEVERITY_ORDER: readonly Severity[] = ["critical", "high", "medium", "low"];

/** rules.model.Finding, exactly. */
export interface Finding {
  rule_id: string;
  severity: Severity;
  sheet: string;
  coordinate: string;
  message: string;
  blast_radius: number;
}

/** A Finding plus what lineage.diff and db.store know about it. */
export interface AnnotatedFinding extends Finding {
  /** From diff_runs: is it in the version before this one? */
  status: "new" | "still_there";
  /** From first_seen: the version it first appeared in. */
  first_seen: number | null;
  /** finding_key(f) in load_approvals: has a person accepted it? */
  approved: boolean;
}

export interface WorkbookStats {
  sheets: number;
  cells: number;
  formulas: number;
  /** Total edges in the dependency graph. */
  links: number;
}

/** GET /api/files/{name}/run */
export interface RunDetail {
  file: string;
  run_id: number;
  version: number;
  previous_version: number | null;
  /** ISO 8601, UTC. */
  created_at: string;
  sha256: string;
  unchanged_since_previous: boolean;
  /** rules.score.risk_score, 0 to 100. */
  score: number;
  stats: WorkbookStats;
  findings: AnnotatedFinding[];
  /** In the previous version, gone from this one. */
  resolved: Finding[];
}

/** GET /api/files */
export interface FileSummary {
  name: string;
  latest_version: number;
  latest_score: number;
  latest_at: string;
  finding_count: number;
}

/** GET /api/files/{name}/history, one per version, oldest first. */
export interface HistoryEntry {
  version: number;
  run_id: number;
  created_at: string;
  score: number;
  sha256: string;
  counts: Record<Severity, number>;
  total: number;
}

export type CellValue = string | number | boolean | null;

export interface RowCell {
  coordinate: string;
  formula: string | null;
  value: CellValue;
  /** The formula with every reference replaced by "#", or null for a typed value. */
  shape: string | null;
  is_target: boolean;
}

/** GET /api/files/{name}/cell?ref=Sheet!A1 */
export interface CellInspect {
  ref: string;
  sheet: string;
  coordinate: string;
  formula: string | null;
  value: CellValue;
  number_format: string;
  /** What this cell reads. Capped at 50, true size in precedents_total. */
  precedents: string[];
  precedents_total: number;
  /** What reads this cell. Capped at 50, true size in dependents_total. */
  dependents: string[];
  dependents_total: number;
  /** Every cell affected downstream. */
  blast_radius: number;
  /** At most 8 cells either side of the target. */
  row: RowCell[];
  row_total: number;
  /** The most common shape across the whole row. */
  majority_shape: string | null;
  /** Cells in the whole row with majority_shape, counted before the window is cut. */
  majority_count: number;
  /** Cells in the whole row holding a formula, counted before the window is cut. */
  formula_count: number;
}

/** One verified passage, built by guardrails.citation_details. */
export interface Citation {
  source: string;
  title: string;
  url: string;
  page: number | null;
  section: string | null;
  quote: string;
}

/** POST /api/explain, exactly agents.standards.StandardsResult. */
export interface Explanation {
  supported: boolean;
  explanation: string;
  citations: Citation[];
  evidence_scope: "contextual" | "none";
}

/** GET /api/files/{name}/approvals, one row per human decision. */
export interface Approval {
  rule_id: string;
  sheet: string;
  coordinate: string;
  reason: string;
  decided_by: string;
  decided_at: string;
}

/** GET /api/health */
/** auth.User.public(): GET /api/auth/me and POST /api/auth/login. */
export type Role = "analyst" | "reviewer" | "signer";

export interface Account {
  username: string;
  role: Role;
  /** auth.CAN_UPLOAD: analysts and reviewers. */
  can_upload: boolean;
  /** auth.CAN_DECIDE: reviewers only (segregation of duties). */
  can_decide: boolean;
}

export interface Health {
  ok: boolean;
  database: boolean;
  llm: boolean;
  version: string;
}

/** GET /api/evaluation, docs/evaluation.json as it is. */
export interface EvaluationTier {
  tier: number;
  name: string;
  dataset: string;
  precision: number | null;
  recall: number | null;
  script: string;
  reading: string;
  true_positives?: number;
  false_positives?: number;
  /** Tier 2: how many of the false positives one rule produced. */
  dead_input_false_positives?: number;
  scanned?: number;
  failed_to_parse?: number;
  triggered?: number;
  trigger_rate?: number;
  findings_per_workbook?: { median: number; mean: number; max: number };
  by_rule?: { rule_id: string; workbooks: number; share: number }[];
}

export interface EvaluationReport {
  source: string;
  tiers: EvaluationTier[];
  retrieval: {
    questions: number;
    corpus_chunks: number;
    documents: { k: number; hits: number }[];
    passages: { k: number; hits: number }[];
    script: string;
    caveat: string;
  };
  comparison: { label: string; value?: number; range?: [number, number] }[];
}

/** Which data source the session is reading from. */
export type DataMode = "live" | "sample";
