"""A valid quote cannot justify a made-up cell or URL in the explanation."""

import json
from types import SimpleNamespace

import pytest

from finlint.agents.standards import explain_finding
from finlint.rules.model import Finding


QUOTE = "Reliable financial information should be reviewed before it is used."
FINDING = Finding(
    rule_id="hardcoded_value", severity="high", sheet="P&L", coordinate="C1",
    message="A typed value appears between formulas",
)


@pytest.mark.parametrize("explanation", [
    "Review invented cell Z999.",
    "See https://made-up.example/rule for this requirement.",
])
def test_standards_discards_explanation_with_invented_location(explanation):
    chunk = SimpleNamespace(
        source="guide.pdf", title="Guide", url="https://example.org/guide.pdf",
        page=5, section=None, text=QUOTE, chunk_index=0,
    )
    hit = SimpleNamespace(chunk=chunk, score=0.8, neighbors=[])
    reply = json.dumps({
        "action": "answer", "explanation": explanation,
        "citations": [{"evidence_id": 0, "quote": QUOTE}],
    })

    result = explain_finding(FINDING, lambda query: [hit], lambda system, user: reply)
    assert result.supported is False
    assert not result.citations
