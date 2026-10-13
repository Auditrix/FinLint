"""Check whether search finds passages whose source location we know."""

import argparse
import csv
import json
from pathlib import Path

from finlint.rag.store import connect, search


ROOT = Path(__file__).resolve().parents[1]
QUESTIONS = ROOT / "docs" / "retrieval_questions.tsv"


def read_questions(path):
    with open(path, encoding="utf-8", newline="") as file:
        cases = list(csv.DictReader(file, delimiter="\t"))

    ids = [case["id"] for case in cases]
    if not cases or len(ids) != len(set(ids)):
        raise ValueError("Questions must have unique ids")
    for case in cases:
        if not case["question"] or not case["source"] or not case["anchor"]:
            raise ValueError(f"Incomplete question {case['id']}")
        if bool(case["page"]) == bool(case["section"]):
            raise ValueError(f"Question {case['id']} needs a page or section")
        case["page"] = int(case["page"]) if case["page"] else None
    return cases


def same_location(row, case):
    if row["source"] != case["source"]:
        return False
    if case["page"] is not None:
        return row["page"] == case["page"]
    return row["section"] == case["section"]


def rank_of(rows, case):
    for rank, row in enumerate(rows, start=1):
        if same_location(row, case):
            return rank
    return None


def check_anchor(conn, case):
    if case["page"] is not None:
        rows = conn.execute(
            "SELECT text FROM chunks WHERE source = %s AND page = %s ORDER BY chunk_index",
            (case["source"], case["page"]),
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT text FROM chunks WHERE source = %s AND section = %s ORDER BY chunk_index",
            (case["source"], case["section"]),
        ).fetchall()

    # PDF line breaks are not meaningful for checking a short answer passage.
    page_text = " ".join(" ".join(row[0].split()) for row in rows).casefold()
    anchor = " ".join(case["anchor"].split()).casefold()
    if anchor not in page_text:
        raise ValueError(f"Question {case['id']} has no matching passage in the database")


def score_cases(cases, find):
    results = []
    for case in cases:
        rows = find(case["question"], 10)
        rank = rank_of(rows, case)
        source_rank = next(
            (i for i, row in enumerate(rows, start=1) if row["source"] == case["source"]),
            None,
        )
        results.append({
            "id": case["id"],
            "question": case["question"],
            "expected_source": case["source"],
            "expected_page": case["page"],
            "expected_section": case["section"] or None,
            "location_rank": rank,
            "source_rank": source_rank,
            "top_source": rows[0]["source"] if rows else None,
            "top_page": rows[0]["page"] if rows else None,
            "top_section": rows[0]["section"] if rows else None,
        })

    count = len(results)
    return {
        "evaluation_type": "Known-passage questions selected from the corpus, not a blind test",
        "questions": count,
        "location_hits": {
            str(k): sum(r["location_rank"] is not None and r["location_rank"] <= k for r in results)
            for k in (1, 5, 10)
        },
        "source_hits": {
            str(k): sum(r["source_rank"] is not None and r["source_rank"] <= k for r in results)
            for k in (1, 5, 10)
        },
        "results": results,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--questions", type=Path, default=QUESTIONS)
    parser.add_argument("--output", type=Path, default=ROOT / "data/generated/week5_retrieval_50.json")
    args = parser.parse_args()

    cases = read_questions(args.questions)
    conn = connect()
    try:
        missing = []
        for case in cases:
            try:
                check_anchor(conn, case)
            except ValueError:
                missing.append(case["id"])
        if missing:
            raise ValueError(f"Passages not found for question ids: {', '.join(missing)}")
        report = score_cases(cases, lambda question, limit: search(conn, question, limit))
    finally:
        conn.close()

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(f"Checked {report['questions']} questions against passages in the database")
    print("Correct location in top 1/5/10:", report["location_hits"])
    print("Correct source in top 1/5/10:", report["source_hits"])
    print("Report:", args.output)


if __name__ == "__main__":
    main()
