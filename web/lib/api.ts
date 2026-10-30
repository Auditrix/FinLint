/**
 * The one place the frontend talks to the backend.
 *
 * On start it asks /api/health with a short timeout. If the API answers, the
 * session is "live" and every call goes to it. If not, the session is
 * "sample" and reads go to /fixtures, which scripts/export_ui_fixture.py
 * filled with a real run of the real engine. The UI shows a banner saying
 * which, so sample data is never mistaken for a live check.
 *
 * Writes in sample mode stay honest: a new check needs the engine, so it is
 * refused with a reason; an approval is kept in this browser only and says so.
 */

import type {
  Account,
  Approval,
  CellInspect,
  DataMode,
  EvaluationReport,
  Explanation,
  FileSummary,
  Finding,
  Health,
  HistoryEntry,
  RunDetail,
} from "./types";
import { cellRef } from "./utils";

const BASE = process.env.NEXT_PUBLIC_API_BASE ?? "";
// Generous on purpose. On Windows a refused connection takes about two seconds
// (measured), and "localhost" can try IPv6 first and fall back to IPv4, so a
// shorter limit could switch to the sample while the real API was up.
const HEALTH_TIMEOUT_MS = 4000;

export class ApiError extends Error {
  constructor(
    message: string,
    readonly status: number,
  ) {
    super(message);
  }
}

let connection: Promise<{ mode: DataMode; health: Health }> | null = null;

/**
 * Decide once per session where data comes from. Every caller shares the one
 * in-flight request, so reads that start together do not each probe health,
 * and none of them can run before the decision is made.
 */
export function connect(): Promise<{ mode: DataMode; health: Health }> {
  connection ??= (async () => {
    try {
      const controller = new AbortController();
      const timer = setTimeout(() => controller.abort(), HEALTH_TIMEOUT_MS);
      const res = await fetch(`${BASE}/api/health`, { signal: controller.signal });
      clearTimeout(timer);
      if (!res.ok) throw new Error(`health ${res.status}`);
      return { mode: "live" as const, health: (await res.json()) as Health };
    } catch {
      return { mode: "sample" as const, health: await fixture<Health>("health.json") };
    }
  })();
  return connection;
}

async function fixture<T>(name: string): Promise<T> {
  const res = await fetch(`/fixtures/${name}`);
  if (!res.ok) throw new ApiError(`Sample data ${name} is missing`, res.status);
  return (await res.json()) as T;
}

// Called when the API says the session is gone (expired, or signed out in
// another tab), so the workspace can show the sign in screen instead of a
// row of errors.
let onSignedOut: (() => void) | null = null;

export function whenSignedOut(handler: (() => void) | null): void {
  onSignedOut = handler;
}

async function live<T>(path: string, init?: RequestInit): Promise<T> {
  // "include" sends the session cookie. In development the page is on port
  // 3000 and the API on 8000, which counts as another origin.
  const res = await fetch(`${BASE}${path}`, { ...init, credentials: "include" });
  if (res.status === 401 && !path.startsWith("/api/auth/")) onSignedOut?.();
  if (!res.ok) {
    let detail = `The server answered ${res.status}.`;
    try {
      const body = (await res.json()) as { detail?: unknown };
      if (typeof body.detail === "string") detail = body.detail;
    } catch {
      /* body was not JSON; keep the status line */
    }
    throw new ApiError(detail, res.status);
  }
  return (await res.json()) as T;
}

function enc(value: string): string {
  return encodeURIComponent(value);
}

// Sample data that is loaded once and reused. A failed load is forgotten
// rather than cached, so one network blip does not break every later lookup
// until the page is reloaded.
let sampleCells: Promise<Record<string, CellInspect>> | null = null;
let sampleExplanations: Promise<Record<string, Explanation>> | null = null;
let sampleRun: Promise<RunDetail> | null = null;

function once<T>(load: () => Promise<T>, keep: (p: Promise<T> | null) => void): Promise<T> {
  const p = load();
  keep(p);
  p.catch(() => keep(null));
  return p;
}

// Decisions recorded in sample mode. In memory only: a reload clears them.
const sampleApprovals: Approval[] = [];

function approvalKey(a: { rule_id: string; sheet: string; coordinate: string }): string {
  return `${a.rule_id}|${a.sheet}|${a.coordinate}`;
}

/**
 * The saved sample covers exactly one workbook. Asking it about any other
 * name must fail loudly, never quietly return this workbook's data under the
 * other name.
 */
async function sampleRunFor(file: string): Promise<RunDetail> {
  const run = await (sampleRun ?? once(() => fixture<RunDetail>("run.json"), (p) => (sampleRun = p)));
  if (run.file !== file) {
    throw new ApiError(
      `The saved sample only covers ${run.file}. Start the API to open ${file}.`,
      404,
    );
  }
  return run;
}

/** Every read waits for the live or sample decision before choosing a source. */
async function ready(): Promise<DataMode> {
  return (await connect()).mode;
}

/** The account signed in, or null when nobody is. Throws on anything else. */
export async function getAccount(): Promise<Account | null> {
  try {
    return await live<Account>("/api/auth/me");
  } catch (e) {
    if (e instanceof ApiError && e.status === 401) {
      // "No accounts exist yet" is worth showing on the sign in screen.
      if (e.message.startsWith("No accounts")) throw e;
      return null;
    }
    throw e;
  }
}

export async function signIn(username: string, password: string): Promise<Account> {
  return live("/api/auth/login", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ username, password }),
  });
}

export async function signOut(): Promise<void> {
  await live("/api/auth/logout", { method: "POST" });
}

export async function getFiles(): Promise<FileSummary[]> {
  return (await ready()) === "live" ? live("/api/files") : fixture("files.json");
}

export async function getRun(file: string): Promise<RunDetail> {
  if ((await ready()) === "live") return live(`/api/files/${enc(file)}/run`);
  const run = await sampleRunFor(file);
  // The saved approvals and this browser's sample decisions together decide
  // which findings read as accepted, the same set the audit log shows.
  const accepted = new Set([...(await sampleSavedApprovals()), ...sampleApprovals].map(approvalKey));
  return {
    ...run,
    findings: run.findings.map((f) => ({ ...f, approved: f.approved || accepted.has(approvalKey(f)) })),
  };
}

export async function getHistory(file: string): Promise<HistoryEntry[]> {
  if ((await ready()) === "live") return live(`/api/files/${enc(file)}/history`);
  await sampleRunFor(file);
  return fixture("history.json");
}

export async function getCell(file: string, ref: string): Promise<CellInspect> {
  if ((await ready()) === "live") return live(`/api/files/${enc(file)}/cell?ref=${enc(ref)}`);
  await sampleRunFor(file);
  const cells = await (sampleCells ??
    once(() => fixture<Record<string, CellInspect>>("cells.json"), (p) => (sampleCells = p)));
  const cell = cells[ref];
  if (!cell) {
    throw new ApiError(
      "The saved sample only covers cells that have a finding. Connect the API to inspect any cell.",
      404,
    );
  }
  return cell;
}

export async function explain(file: string, finding: Finding): Promise<Explanation> {
  if ((await ready()) === "live") {
    return live("/api/explain", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ file, finding }),
    });
  }
  await sampleRunFor(file);
  const saved = await (sampleExplanations ??
    once(() => fixture<Record<string, Explanation>>("explanations.json"), (p) => (sampleExplanations = p)));
  const hit = saved[`${finding.rule_id}|${cellRef(finding.sheet, finding.coordinate)}`];
  if (!hit) {
    throw new ApiError(
      "The saved sample has a standards check for one finding per rule only. Connect the API to ask about this one.",
      404,
    );
  }
  return hit;
}

async function sampleSavedApprovals(): Promise<Approval[]> {
  return fixture<Approval[]>("approvals.json");
}

export async function getApprovals(file: string): Promise<Approval[]> {
  if ((await ready()) === "live") return live(`/api/files/${enc(file)}/approvals`);
  await sampleRunFor(file);
  return [...(await sampleSavedApprovals()), ...sampleApprovals].sort((a, b) =>
    b.decided_at.localeCompare(a.decided_at),
  );
}

/**
 * Record a decision. In live mode the server records the account signed in as
 * the decider, so no name is sent. The sample has no accounts, so it takes a
 * typed name instead.
 */
export async function approveFinding(
  file: string,
  finding: Finding,
  reason: string,
  who: string,
): Promise<Approval> {
  if ((await ready()) === "live") {
    return live("/api/approvals", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ file, finding, reason }),
    });
  }
  // The same rules db.store.approve enforces, so the sample cannot teach a
  // flow the real system would reject.
  await sampleRunFor(file);
  if (!reason.trim()) throw new ApiError("An approval needs a reason", 400);
  if (!who.trim()) throw new ApiError("An approval needs to say who decided it", 400);
  const approval: Approval = {
    rule_id: finding.rule_id,
    sheet: finding.sheet,
    coordinate: finding.coordinate,
    reason: reason.trim(),
    decided_by: who.trim(),
    decided_at: new Date().toISOString(),
  };
  sampleApprovals.push(approval);
  return approval;
}

export async function checkWorkbook(file: File): Promise<RunDetail> {
  if ((await ready()) !== "live") {
    throw new ApiError("Checking a new workbook needs the engine. Start the API to upload a file.", 503);
  }
  const form = new FormData();
  form.append("file", file);
  return live("/api/check", { method: "POST", body: form });
}

export async function getEvaluation(): Promise<EvaluationReport> {
  return (await ready()) === "live" ? live("/api/evaluation") : fixture("evaluation.json");
}
