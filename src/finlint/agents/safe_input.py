"""Only send the agents the parts of a workbook needed for a decision."""

import re

from finlint.parsing.model import EXCEL_ERRORS


TEXT_LITERAL = re.compile(r'"(?:[^"]|"")*(?:"|$)')
QUOTED_SHEET = re.compile(r"'(?:[^']|'')*'!")
FORMULA_CHARACTERS = re.compile(r"[^A-Za-z0-9_.$!+\-*/^&%=(),:;<>\[\]#]")

RULE_SUMMARIES = {
    "error_cells": "Excel shows an error result.",
    "circular_reference": "The dependency graph contains a circular reference.",
    "dead_input": "This typed number is not read by another formula.",
    "hardcoded_value": "This row mostly contains formulas, but this cell is a typed number.",
    "broken_link": "This formula refers to a missing sheet or another workbook.",
    "formula_drift": "This formula has a different structure from the others in its row.",
}


def has_formula_text(formula):
    return bool(formula and TEXT_LITERAL.search(formula))


def safe_formula(formula):
    if formula is None:
        return None
    shape = TEXT_LITERAL.sub("TEXT", formula)
    shape = QUOTED_SHEET.sub("SHEET!", shape)
    shape = FORMULA_CHARACTERS.sub("", shape)
    return shape[:400]


def safe_value(value):
    if isinstance(value, (bool, int, float)):
        return value
    if isinstance(value, str) and value in EXCEL_ERRORS:
        return value
    if value is None:
        return None
    return "[text or date hidden]"


def safe_finding(finding):
    rule_id = finding.rule_id if finding.rule_id in RULE_SUMMARIES else "other_check"
    return {
        "rule_id": rule_id,
        "description": RULE_SUMMARIES.get(rule_id, "A spreadsheet check found an issue."),
        "severity": finding.severity,
        "blast_radius": finding.blast_radius,
    }
