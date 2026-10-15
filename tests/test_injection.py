"""A hostile workbook cell must stay data, not become a model instruction."""

import json

import pytest

from finlint.agents.auditor import review_findings
from finlint.guardrails.injection import ATTACK_TEXT, make_attack_workbook, run_injection_probe
from finlint.parsing.reader import read_workbook
from finlint.rules.engine import check_workbook


def test_text_cell_attack_does_not_reach_the_model(tmp_path):
    prompts = []

    def complete(system, user):
        prompts.append((system, user))
        return json.dumps({"decisions": [
            {"finding_id": 0, "keep": ATTACK_TEXT not in system + user,
             "reason": "The typed value needs a person's review"}
        ]})

    result = run_injection_probe(tmp_path / "attack.xlsx", complete)
    assert result == {
        "finding_kept": True,
        "attack_reached_model": False,
        "model_calls": 1,
        "workbook_unchanged": True,
    }
    assert len(prompts) == 1
    assert "not instructions" in prompts[0][1]


def test_error_cell_cannot_be_dismissed_by_a_model(tmp_path):
    path = make_attack_workbook(tmp_path / "attack.xlsx")
    finding = next(item for item in check_workbook(path) if item.rule_id == "error_cells")

    def no_model_call(system, user):
        raise AssertionError("An Excel error should be kept without calling a model")

    reviewed = review_findings(read_workbook(path), [finding], no_model_call)
    assert len(reviewed) == 1
    assert reviewed[0].finding.coordinate == "F3"


def test_attack_probe_never_overwrites_an_existing_workbook(tmp_path):
    path = make_attack_workbook(tmp_path / "attack.xlsx")
    original = path.read_bytes()
    with pytest.raises(FileExistsError):
        make_attack_workbook(path)
    assert path.read_bytes() == original
