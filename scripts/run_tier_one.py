"""Score the planted faults in small batches so the full run finishes sooner."""

import argparse
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

from finlint.eval.faults import load_faults
from finlint.eval.score import evaluate_tier_one, save_report
from finlint.rules.engine import run_all


def score_batch(records):
    return evaluate_tier_one(records, run_all)


def metrics(true_positives, false_positives, false_negatives):
    precision = true_positives / (true_positives + false_positives) if true_positives + false_positives else 0.0
    recall = true_positives / (true_positives + false_negatives) if true_positives + false_negatives else 0.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    return {
        "true_positives": true_positives,
        "false_positives": false_positives,
        "false_negatives": false_negatives,
        "precision": round(precision, 4),
        "recall": round(recall, 4),
        "f1": round(f1, 4),
    }


def combine_reports(reports, total_faults):
    tp = sum(report["overall"]["true_positives"] for report in reports)
    fp = sum(report["overall"]["false_positives"] for report in reports)
    by_rule_counts = {}

    for report in reports:
        for rule, numbers in report["by_rule"].items():
            counts = by_rule_counts.setdefault(rule, [0, 0])
            counts[0] += numbers["true_positives"]
            counts[1] += numbers["false_positives"]

    return {
        "overall": metrics(tp, fp, total_faults - tp),
        "by_rule": {
            rule: metrics(counts[0], counts[1], total_faults - counts[0])
            for rule, counts in sorted(by_rule_counts.items())
        },
        "baseline_findings": reports[0]["baseline_findings"] if reports else {},
        "faults_scored": total_faults,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--faults", default="data/generated/fisy_faults.jsonl")
    parser.add_argument("--output", default="data/generated/tier_one_report.json")
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--batch-size", type=int, default=50)
    parser.add_argument("--limit", type=int, default=None)
    args = parser.parse_args()

    records = load_faults(args.faults)
    if args.limit is not None:
        records = records[:args.limit]
    if not records:
        raise ValueError("No fault records to score")
    if args.workers < 1 or args.batch_size < 1:
        raise ValueError("Workers and batch size must be positive")

    batches = [records[i:i + args.batch_size] for i in range(0, len(records), args.batch_size)]
    reports = []
    print(f"Scoring {len(records)} faults in {len(batches)} batches", flush=True)
    with ProcessPoolExecutor(max_workers=args.workers) as pool:
        for number, report in enumerate(pool.map(score_batch, batches), start=1):
            reports.append(report)
            print(f"Finished batch {number}/{len(batches)}", flush=True)

    result = combine_reports(reports, len(records))
    save_report(Path(args.output), result)
    print(result["overall"], flush=True)


if __name__ == "__main__":
    main()
