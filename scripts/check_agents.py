"""Try both agents on one finding from a public seed workbook."""

import argparse

from finlint.agents.auditor import ReviewedFinding, review_findings
from finlint.agents.groq_provider import groq_completion
from finlint.agents.report import write_report
from finlint.agents.standards import explain_with_retriever
from finlint.eval.score import save_report
from finlint.graph.build import build_graph
from finlint.parsing.reader import read_workbook
from finlint.rag.store import connect
from finlint.rules.engine import run_all


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--workbook", default="data/seeds/FISY-ESSENTIEL.xlsx")
    parser.add_argument("--model", default="qwen/qwen3.8-27b")
    parser.add_argument("--rule", default="hardcoded_value")
    parser.add_argument("--output", default="data/generated/week5_agent_check.json")
    args = parser.parse_args()

    workbook = read_workbook(args.workbook)
    graph = build_graph(workbook)
    findings = run_all(workbook, graph)
    finding = next((f for f in findings if f.rule_id == args.rule), None)
    if finding is None:
        raise ValueError(f"No {args.rule} finding in {args.workbook}")
    complete = groq_completion(args.model)

    conn = connect()
    try:
        standards = explain_with_retriever(conn, finding, complete)
    finally:
        conn.close()

    review_error = None
    auditor_model_calls = 0

    def complete_auditor(system, user):
        nonlocal auditor_model_calls
        auditor_model_calls += 1
        return complete(system, user)

    try:
        reviewed = review_findings(workbook, [finding], complete_auditor)
    except ValueError as error:
        reviewed = [ReviewedFinding(
            finding=finding,
            reason="Auditor unavailable; keep this finding for human review.",
        )]
        review_error = str(error)

    written_report = write_report(
        workbook,
        reviewed,
        {(finding.sheet, finding.coordinate): standards},
        complete,
    )

    report = {
        "model": args.model,
        "workbook": args.workbook,
        "finding": finding.model_dump(),
        "standards": standards.model_dump(),
        "auditor_kept_finding": bool(reviewed) if review_error is None else None,
        "auditor_model_calls": auditor_model_calls,
        "auditor_reason": reviewed[0].reason if reviewed else None,
        "auditor_error": review_error,
        "written_report": written_report,
    }
    save_report(args.output, report)
    print("Verified context found:", standards.supported)
    print("Evidence scope:", standards.evidence_scope)
    print("Verified citations:", len(standards.citations))
    print("Auditor kept finding:", report["auditor_kept_finding"])
    print("Auditor model calls:", auditor_model_calls)
    print("Written report:\n" + written_report)
    print("Report:", args.output)
    if review_error:
        raise ValueError(review_error)


if __name__ == "__main__":
    main()
