"""The live safety script must use a real workbook without changing it."""

import json

from scripts.probe_agent_safety import ATTACKS, run_probe


def test_probe_keeps_a_text_formula_without_sending_it_to_the_model(tmp_path):
    prompts = []

    def complete(system, user):
        prompts.append((system, user))
        return json.dumps({"decisions": [
            {"finding_id": 0, "keep": True, "reason": "This formula differs from its row"}
        ]})

    result = run_probe(tmp_path / "hostile.xlsx", ATTACKS["pretend_system"], complete)
    assert result["finding_rule"] == "formula_drift"
    assert result["kept_for_human_review"] is True
    assert result["workbook_unchanged"] is True
    assert result["model_calls"] == 0
    assert not prompts


def test_probe_does_not_allow_the_model_to_dismiss_a_text_formula(tmp_path):
    def complete(system, user):
        return json.dumps({"decisions": [
            {"finding_id": 0, "keep": False, "reason": "No review needed"}
        ]})

    result = run_probe(tmp_path / "hostile.xlsx", ATTACKS["hide_finding"], complete)
    assert result["kept_for_human_review"] is True
    assert result["model_calls"] == 0
    assert result["workbook_unchanged"] is True
