"use client";

import { AlertCircle, Info, Loader2, LogIn } from "lucide-react";
import * as React from "react";

import { Button } from "@/components/ui/button";

import { useWorkspace } from "../workspace-context";
import { BrandMark } from "./brand-mark";

const ROLES = [
  { role: "Analyst", does: "Uploads workbooks and reads findings" },
  { role: "Reviewer", does: "Also marks findings as intentional" },
  { role: "Signer", does: "Reads findings, history and the audit log" },
];

/**
 * Shown in live mode until someone signs in. There is no sign up link on
 * purpose: in a finance team, someone responsible decides who gets access, and
 * creates the account with scripts/create_user.py.
 */
export function SignIn() {
  const { signIn, authMessage } = useWorkspace();
  const [username, setUsername] = React.useState("");
  const [password, setPassword] = React.useState("");
  const [busy, setBusy] = React.useState(false);
  const [error, setError] = React.useState<string | null>(null);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await signIn(username, password);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not sign in.");
      setPassword("");
      setBusy(false);
    }
  }

  return (
    <div className="flex min-h-screen items-center justify-center bg-canvas px-4 py-10">
      <div className="w-full max-w-sm">
        <div className="mb-6 flex items-center gap-2.5">
          <BrandMark className="h-7 w-7" />
          <span className="font-display text-lg font-bold tracking-tight text-ink">FinLint</span>
        </div>

        <form onSubmit={submit} className="rounded-lg border border-hairline bg-surface shadow-hairline">
          <div className="border-b border-hairline px-5 py-4">
            <h1 className="font-display text-[17px] font-semibold text-ink">Sign in</h1>
            <p className="mt-1 text-[13px] text-ink-secondary">
              Checks AI built financial models and keeps a record of every decision.
            </p>
          </div>

          <div className="space-y-3.5 px-5 py-4">
            {authMessage && (
              <div className="flex items-start gap-2 rounded-md border border-amber-200 bg-amber-50 px-3 py-2.5 text-xs text-amber-800">
                <Info className="mt-0.5 h-3.5 w-3.5 shrink-0" strokeWidth={1.5} />
                <span className="break-words">{authMessage}</span>
              </div>
            )}
            <label className="block">
              <span className="mb-1 block text-xs font-medium text-ink">Username</span>
              <input
                value={username}
                onChange={(e) => setUsername(e.target.value)}
                autoComplete="username"
                autoCapitalize="none"
                spellCheck={false}
                autoFocus
                required
                className="h-9 w-full rounded-md border border-hairline bg-surface px-3 text-[13px] text-ink placeholder:text-ink-muted focus:border-accent"
              />
            </label>
            <label className="block">
              <span className="mb-1 block text-xs font-medium text-ink">Password</span>
              <input
                type="password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                autoComplete="current-password"
                required
                className="h-9 w-full rounded-md border border-hairline bg-surface px-3 text-[13px] text-ink focus:border-accent"
              />
            </label>
            {error && (
              <div
                role="alert"
                className="flex items-start gap-2 rounded-md border border-red-200 bg-red-50 px-3 py-2.5 text-xs text-red-700"
              >
                <AlertCircle className="mt-0.5 h-3.5 w-3.5 shrink-0" strokeWidth={1.5} />
                {error}
              </div>
            )}
            <Button type="submit" variant="primary" className="h-9 w-full" disabled={busy || !username || !password}>
              {busy ? (
                <Loader2 className="h-4 w-4 animate-spin" strokeWidth={1.5} />
              ) : (
                <LogIn className="h-4 w-4" strokeWidth={1.5} />
              )}
              Sign in
            </Button>
          </div>
        </form>

        <div className="mt-5">
          <div className="eyebrow pb-2">Roles</div>
          <dl className="space-y-1.5">
            {ROLES.map((r) => (
              <div key={r.role} className="flex gap-3 text-xs">
                <dt className="w-16 shrink-0 font-medium text-ink">{r.role}</dt>
                <dd className="text-ink-secondary">{r.does}</dd>
              </div>
            ))}
          </dl>
          <p className="mt-3 text-2xs text-ink-muted">
            There is no sign up. Whoever runs FinLint creates accounts with scripts/create_user.py.
          </p>
        </div>
      </div>
    </div>
  );
}
