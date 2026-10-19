"""Tier 3: run the rule engine over real AI generated workbooks.

WHAT MAKES TIER 3 DIFFERENT FROM TIER 1 AND TIER 2
    Tier 1 scores planted faults, where we know every answer because we broke
    the file ourselves. Tier 2 scores the ExceLint workbooks, where somebody
    else wrote down the answers. Tier 3 has NO answer key at all.

    So precision and recall cannot be computed here. What can be measured is
    the TRIGGER RATE: out of every workbook, how many did the engine complain
    about, and how loudly. That number alone says whether the tool would be
    usable in practice. A tool that flags 100 percent of files is a tool nobody
    opens twice.

    For a false positive estimate, a sample of workbooks is written out to a
    CSV with an empty verdict column. A human reads those findings and marks
    each one right or wrong. 30 workbooks is the agreed sample size. That hand
    marked file is the only source of truth Tier 3 ever gets.

WHY THE ERRORS ARE COUNTED AND NOT RAISED
    These are real files made by 17 different AI models, not clean fixtures.
    Some will be malformed. A crash on file 200 of 501 would throw away the
    whole run, so every workbook is read inside a try and the failures are
    counted and reported. The failure count is itself a result worth printing.

USAGE, from the repository root:
    python scripts/run_tier_three.py
    python scripts/run_tier_three.py --limit 20          # quick smoke run
    python scripts/run_tier_three.py --sample-size 30    # audit sample size

It writes two files into data/generated/:
    tier_three_report.json     the trigger rate and the per rule breakdown
    tier_three_audit_sample.csv  the findings to mark by hand
"""

import argparse
import csv
import json
import random
from collections import Counter
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

from finlint.rules.engine import check_workbook

# Fixed so the same 30 workbooks come back on every run. If the sample changed
# each time, the hand marking work would have to start again from scratch.
RANDOM_SEED = 42


def find_workbooks(arena_dir: Path) -> list[Path]:
    """Every .xlsx under the Arena folder, in a fixed order.

    Sorted because the operating system does not promise an order, and the
    audit sample has to be reproducible.
    """
    return sorted(arena_dir.rglob("*.xlsx"))


def workbook_id(path: Path, arena_dir: Path) -> str:
    """A short name for one workbook.

    Arena stores each one as outputs/<hash>/sheet.xlsx, so the parent folder is
    the useful identifier and the file name is always "sheet".
    """
    try:
        relative = path.relative_to(arena_dir)
    except ValueError:
        return path.stem
    return relative.parent.name or path.stem


def scan_one(path_text: str) -> dict:
    """Check one workbook and return a plain dictionary of what was found.

    Returns a dictionary rather than Finding objects because this runs inside a
    worker process, and anything crossing a process boundary has to be picklable
    and cheap to send back.
    """
    path = Path(path_text)
    try:
        findings = check_workbook(path)
    except Exception as error:
        # The type name is kept, not the message, because messages contain file
        # paths and are too noisy to group by.
        return {"path": path_text, "error": type(error).__name__, "findings": []}

    return {
        "path": path_text,
        "error": None,
        "findings": [
            {
                "rule_id": finding.rule_id,
                "severity": finding.severity,
                "sheet": finding.sheet,
                "coordinate": finding.coordinate,
                "message": finding.message,
                "blast_radius": finding.blast_radius,
            }
            for finding in findings
        ],
    }


def summarise(results: list[dict], arena_dir: Path) -> dict:
    """Turn the per workbook results into the numbers that go in the report."""
    scanned = [r for r in results if r["error"] is None]
    failed = [r for r in results if r["error"] is not None]

    triggered = [r for r in scanned if r["findings"]]
    counts = sorted(len(r["findings"]) for r in scanned)

    # Workbooks per rule, not findings per rule. One workbook with 80 hardcodes
    # should count once here, otherwise a single noisy file hides everything else.
    workbooks_per_rule = Counter()
    findings_per_rule = Counter()
    findings_per_severity = Counter()
    for result in scanned:
        rules_seen = set()
        for finding in result["findings"]:
            findings_per_rule[finding["rule_id"]] += 1
            findings_per_severity[finding["severity"]] += 1
            rules_seen.add(finding["rule_id"])
        for rule in rules_seen:
            workbooks_per_rule[rule] += 1

    total_findings = sum(counts)
    return {
        "evaluation_type": "tier_three_unlabelled",
        "workbooks_found": len(results),
        "workbooks_scanned": len(scanned),
        "workbooks_failed": len(failed),
        "failure_types": dict(Counter(r["error"] for r in failed)),
        "trigger_rate": round(len(triggered) / len(scanned), 4) if scanned else 0.0,
        "workbooks_triggered": len(triggered),
        "total_findings": total_findings,
        "findings_per_workbook": {
            "mean": round(total_findings / len(scanned), 2) if scanned else 0.0,
            "median": counts[len(counts) // 2] if counts else 0,
            "max": counts[-1] if counts else 0,
            "zero_findings": sum(1 for c in counts if c == 0),
        },
        "workbooks_per_rule": dict(workbooks_per_rule.most_common()),
        "findings_per_rule": dict(findings_per_rule.most_common()),
        "findings_per_severity": dict(findings_per_severity.most_common()),
        "noisiest_workbooks": [
            {"workbook": workbook_id(Path(r["path"]), arena_dir), "findings": len(r["findings"])}
            for r in sorted(scanned, key=lambda r: -len(r["findings"]))[:10]
        ],
    }


def write_audit_sample(results, arena_dir: Path, out_path: Path, sample_size: int) -> int:
    """Write the findings of a random sample of workbooks, for marking by hand.

    Only workbooks that actually produced a finding are sampled, because a
    workbook with nothing to mark teaches the reviewer nothing about false
    positives.

    The verdict column is left empty on purpose. A human writes "correct" or
    "wrong" in each row, and the share of "wrong" is the false positive
    estimate. That is the whole point of Tier 3.
    """
    triggered = [r for r in results if r["error"] is None and r["findings"]]
    rng = random.Random(RANDOM_SEED)
    sample = rng.sample(triggered, min(sample_size, len(triggered)))
    sample.sort(key=lambda r: r["path"])

    with open(out_path, "w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(
            ["workbook", "sheet", "coordinate", "rule_id", "severity",
             "blast_radius", "message", "verdict", "reviewer_note"]
        )
        rows = 0
        for result in sample:
            name = workbook_id(Path(result["path"]), arena_dir)
            for finding in result["findings"]:
                writer.writerow([
                    name,
                    finding["sheet"],
                    finding["coordinate"],
                    finding["rule_id"],
                    finding["severity"],
                    finding["blast_radius"],
                    finding["message"],
                    "",   # verdict: fill in "correct" or "wrong"
                    "",   # reviewer_note: why, in a few words
                ])
                rows += 1
    return rows


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--arena", default="data/benchmarks/arena")
    parser.add_argument("--output", default="data/generated/tier_three_report.json")
    parser.add_argument("--sample-output", default="data/generated/tier_three_audit_sample.csv")
    parser.add_argument("--sample-size", type=int, default=30)
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--limit", type=int, default=None)
    args = parser.parse_args()

    arena_dir = Path(args.arena)
    if not arena_dir.exists():
        raise SystemExit(f"Arena folder not found: {arena_dir}")

    paths = find_workbooks(arena_dir)
    if args.limit is not None:
        paths = paths[: args.limit]
    if not paths:
        raise SystemExit(f"No .xlsx files under {arena_dir}")

    print(f"Scanning {len(paths)} workbooks with {args.workers} workers", flush=True)

    results = []
    with ProcessPoolExecutor(max_workers=args.workers) as pool:
        for number, result in enumerate(pool.map(scan_one, [str(p) for p in paths]), start=1):
            results.append(result)
            if number % 25 == 0 or number == len(paths):
                print(f"  {number}/{len(paths)}", flush=True)

    report = summarise(results, arena_dir)

    out_path = Path(args.output)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(report, indent=2), encoding="utf-8")

    sample_path = Path(args.sample_output)
    rows = write_audit_sample(results, arena_dir, sample_path, args.sample_size)

    print("\n" + "=" * 60)
    print("TIER 3 RESULT (no labels exist, so this is a trigger rate)")
    print("=" * 60)
    print(f"workbooks scanned   {report['workbooks_scanned']}")
    print(f"workbooks failed    {report['workbooks_failed']}  {report['failure_types']}")
    print(f"trigger rate        {report['trigger_rate']:.1%} "
          f"({report['workbooks_triggered']} of {report['workbooks_scanned']})")
    print(f"findings per book   mean {report['findings_per_workbook']['mean']}, "
          f"median {report['findings_per_workbook']['median']}, "
          f"max {report['findings_per_workbook']['max']}")
    print("\nworkbooks triggering each rule:")
    for rule, count in report["workbooks_per_rule"].items():
        share = count / report["workbooks_scanned"] if report["workbooks_scanned"] else 0
        print(f"  {rule:<20} {count:>5}  ({share:.1%} of workbooks)")

    print(f"\nwrote {out_path}")
    print(f"wrote {sample_path}  ({rows} findings across "
          f"{min(args.sample_size, report['workbooks_triggered'])} workbooks to mark by hand)")
    print("\nNEXT STEP, BY HAND: open the CSV, write correct or wrong in the")
    print("verdict column for every row. The share of wrong is the false")
    print("positive estimate. Published spreadsheet auditors run at 78 to 90")
    print("percent false positives, so an honest number here is a result.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
