"""A small workbook can travel through all of the Week 5 pieces."""

import json
from types import SimpleNamespace

from finlint.agents.auditor import review_findings
from finlint.agents.report import write_report
from finlint.agents.standards import explain_finding
from finlint.guardrails.injection import ATTACK_TEXT, make_attack_workbook
from finlint.parsing.reader import read_workbook
from finlint.rules.engine import check_workbook


QUOTE = "Financial records should be checked for accuracy before they are used."


def test_week5_flow_with_a_hostile_text_cell(tmp_path):
    path = make_attack_workbook(tmp_path / "attack.xlsx")
    workbook = read_workbook(path)
    finding = next(item for item in check_workbook(path)
                   if item.rule_id == "hardcoded_value")
    chunk = SimpleNamespace(
        source="guide.pdf", title="Example Financial Guide",
        url="https://example.org/guide.pdf", page=12,
        section="Approximate heading", text=QUOTE, chunk_index=0,
    )
    hit = SimpleNamespace(chunk=chunk, score=0.8, neighbors=[])
    prompts = []

    def complete(system, user):
        prompts.append((system, user))
        if "public standards" in system:
            return json.dumps({
                "action": "answer", "explanation": "This is general review context.",
                "citations": [{"evidence_id": 0, "quote": QUOTE}],
            })
        if "spreadsheet findings" in system:
            return json.dumps({"decisions": [
                {"finding_id": 0, "keep": True, "reason": "Review this typed value"}
            ]})
        return json.dumps({"overview": "A person should inspect the flagged value."})

    standards = explain_finding(finding, lambda query: [hit], complete)
    reviewed = review_findings(workbook, [finding], complete)
    report = write_report(
        workbook, reviewed, {(finding.sheet, finding.coordinate): standards}, complete,
    )

    assert standards.supported is True
    assert len(reviewed) == 1
    assert len(prompts) == 3
    assert all(ATTACK_TEXT not in system + user for system, user in prompts)
    assert "P&L!C1" in report
    assert "Example Financial Guide, page 12" in report
    assert QUOTE in report
    assert "Approximate heading" not in report
    assert ATTACK_TEXT not in report
