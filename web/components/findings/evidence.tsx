"use client";

import { AlertCircle, BookOpenCheck, ExternalLink, Loader2, SearchX } from "lucide-react";
import * as React from "react";

import { Button } from "@/components/ui/button";
import { Tag } from "@/components/ui/pill";
import * as api from "@/lib/api";
import type { Explanation, Finding } from "@/lib/types";

import { useWorkspace } from "../workspace-context";

/**
 * The Standards agent, asked for one finding. Every quote it returns was
 * already found word for word in the stored document by the citation
 * guardrail, and the source, page and link come from that stored chunk, never
 * from the model. If nothing passed, nothing is shown, and that is said plainly.
 */
export function Evidence({ file, finding }: { file: string; finding: Finding }) {
  const { mode, health } = useWorkspace();
  const [result, setResult] = React.useState<Explanation | null>(null);
  const [busy, setBusy] = React.useState(false);
  const [error, setError] = React.useState<string | null>(null);

  const key = `${finding.rule_id}|${finding.sheet}|${finding.coordinate}`;
  React.useEffect(() => {
    setResult(null);
    setError(null);
    setBusy(false);
  }, [key]);

  const liveWithoutKey = mode === "live" && !health?.llm;

  async function ask() {
    setBusy(true);
    setError(null);
    try {
      setResult(await api.explain(file, finding));
    } catch (e) {
      setError(e instanceof Error ? e.message : "The standards check did not finish.");
    } finally {
      setBusy(false);
    }
  }

  if (!result) {
    return (
      <div className="space-y-2.5">
        <p className="text-[13px] text-ink-secondary">
          Search the public government accounting corpus for a passage relevant to this finding. A quote is shown only
          if it is found word for word in the source.
        </p>
        <Button onClick={ask} disabled={busy || liveWithoutKey}>
          {busy ? (
            <Loader2 className="h-4 w-4 animate-spin" strokeWidth={1.5} />
          ) : (
            <BookOpenCheck className="h-4 w-4" strokeWidth={1.5} />
          )}
          {busy ? "Searching the corpus" : "Find a supporting standard"}
        </Button>
        {liveWithoutKey && <p className="text-xs text-ink-muted">Set GROQ_API_KEY on the server to enable this.</p>}
        {error && (
          <div className="flex items-start gap-2 rounded-md border border-hairline bg-canvas px-3 py-2.5 text-xs text-ink-secondary">
            <AlertCircle className="mt-0.5 h-3.5 w-3.5 shrink-0 text-ink-muted" strokeWidth={1.5} />
            {error}
          </div>
        )}
      </div>
    );
  }

  if (!result.supported || result.citations.length === 0) {
    // Two different outcomes, which must not share one explanation. A decline
    // is the agent stopping before quoting anything, so no citation check ever
    // ran. "No verifiable standard" means it tried and nothing passed.
    const declined = result.explanation === "Request declined";
    return (
      <div className="flex items-start gap-2.5 rounded-md border border-hairline bg-canvas px-3 py-3">
        <SearchX className="mt-0.5 h-4 w-4 shrink-0 text-ink-muted" strokeWidth={1.5} />
        <div className="text-[13px]">
          <div className="font-medium text-ink">
            {declined ? "The standards agent declined" : result.explanation || "No verifiable standard found"}
          </div>
          <p className="mt-0.5 text-xs text-ink-secondary">
            {declined
              ? "It judged that nothing in the corpus applies to this finding, so it quoted nothing rather than stretch a passage to fit. The finding itself still stands."
              : "It searched, but no quote passed the check that the words appear exactly in the source, so none is shown rather than a vague one. The finding itself still stands."}
          </p>
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-2.5">
      <div className="flex items-center gap-2">
        <Tag tone="info" mono={false}>
          Context, not proof
        </Tag>
        <span className="text-xs text-ink-muted">A relevant principle, not evidence that this cell is wrong</span>
      </div>
      <p className="text-[13px] leading-relaxed text-ink-secondary">{stripPreamble(result.explanation)}</p>
      {result.citations.map((c, i) => (
        <figure key={i} className="overflow-hidden rounded-md border border-hairline">
          <blockquote className="bg-recessed px-3.5 py-3 text-[13px] leading-relaxed text-ink">
            <span className="mr-0.5 font-display text-base leading-none text-slate-400">&ldquo;</span>
            {c.quote}
            <span className="ml-0.5 font-display text-base leading-none text-slate-400">&rdquo;</span>
          </blockquote>
          <figcaption className="flex flex-wrap items-center justify-between gap-2 border-t border-hairline bg-surface px-3.5 py-2">
            <div className="min-w-0">
              <div className="truncate text-xs font-medium text-ink">{c.title}</div>
              <div className="font-mono text-2xs text-ink-muted">
                {c.page !== null ? `page ${c.page}` : c.section ? `section ${c.section}` : c.source}
                {c.page !== null && c.section ? ` · nearest heading ${c.section}` : ""}
              </div>
            </div>
            <a
              href={c.page !== null ? `${c.url}#page=${c.page}` : c.url}
              target="_blank"
              rel="noreferrer"
              className="inline-flex items-center gap-1 text-xs font-medium text-accent hover:underline"
            >
              Open the source
              <ExternalLink className="h-3 w-3" strokeWidth={1.5} />
            </a>
          </figcaption>
        </figure>
      ))}
    </div>
  );
}

// The agent prefixes every supported answer with the same caveat. The tag
// above already says it, so the sentence is not repeated underneath.
function stripPreamble(text: string): string {
  return text.replace(/^Context only; the citation does not prove this cell is wrong\.\s*/, "");
}
