"""The report writes checked locations and citations, not model inventions."""

import json
from types import SimpleNamespace

import pytest

from finlint.agents.auditor import ReviewedFinding
from finlint.agents.report import write_report
from finlint.agents.standards import StandardsResult
from finlint.guardrails.citation_details import citation_details
from finlint.guardrails.injection import ATTACK_TEXT, make_attack_workbook
from finlint.parsing.reader import read_workbook
from finlint.rules.engine import check_workbook


QUOTE = "Financial information should be reviewed for accuracy before it is used."


def example(tmp_path):
    path = make_attack_workbook(tmp_path / "attack.xlsx")
    workbook = read_workbook(path)
    finding = next(item for item in check_workbook(path)
                   if item.rule_id == "hardcoded_value")
    reviewed = ReviewedFinding(finding=finding, reason="A person should review this value")
    chunk = SimpleNamespace(
        source="guide.pdf", title="Example Financial Guide",
        url="https://example.org/guide.pdf", page=54,
        section="Wrong outline heading", text=QUOTE, chunk_index=0,
    )
    citation = citation_details(SimpleNamespace(chunk=chunk, neighbors=[]), QUOTE)
    standards = StandardsResult(
        supported=True, explanation="Context only", citations=[citation],
        evidence_scope="contextual",
    )
    return workbook, reviewed, standards


def test_report_uses_checked_cell_and_source_fields(tmp_path):
    workbook, reviewed, standards = example(tmp_path)
    prompts = []

    def complete(system, user):
        prompts.append((system, user))
        return json.dumps({"overview": "A person should inspect the flagged value before using this workbook."})

    report = write_report(
        workbook, [reviewed], {("P&L", "C1"): standards}, complete,
    )
    assert len(prompts) == 1
    assert ATTACK_TEXT not in prompts[0][0] + prompts[0][1]
    assert ATTACK_TEXT not in report
    assert "P&L!C1" in report
    assert "Example Financial Guide, page 54" in report
    assert "https://example.org/guide.pdf" in report
    assert QUOTE in report
    assert "Wrong outline heading" not in report
    assert "does not prove the cell is wrong" in report


def test_report_drops_a_cell_that_is_not_in_the_workbook(tmp_path):
    workbook, reviewed, _ = example(tmp_path)
    invented = reviewed.model_copy(deep=True)
    invented.finding.coordinate = "Z999"

    def no_model_call(system, user):
        raise AssertionError("There are no real findings to summarize")

    report = write_report(workbook, [invented], complete=no_model_call)
    assert "Z999" not in report
    assert "Findings for human review: 0" in report
    assert "Locations not found in workbook and omitted: 1" in report
    assert "does not prove the workbook is error-free" in report


@pytest.mark.parametrize("overview", [
    "The problem is at Z999.",
    "See https://made-up.example/rule for the answer.",
    "Buy this stock before reviewing the model.",
])
def test_report_drops_unsafe_model_overview(tmp_path, overview):
    workbook, reviewed, _ = example(tmp_path)
    report = write_report(
        workbook, [reviewed],
        complete=lambda system, user: json.dumps({"overview": overview}),
    )
    assert overview not in report
    assert "Automated overview unavailable" in report
    assert "P&L!C1" in report


def test_report_keeps_findings_when_model_returns_bad_json(tmp_path):
    workbook, reviewed, _ = example(tmp_path)
    report = write_report(workbook, [reviewed], complete=lambda system, user: "not json")
    assert "P&L!C1" in report
    assert "Automated overview unavailable" in report
    assert "Source: No checked citation attached." in report
