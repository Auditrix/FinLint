"""Small checks for the retrieval evaluation script, without a live database."""

import pytest

from scripts.evaluate_retrieval import check_anchor, rank_of, read_questions, score_cases


def test_question_file_has_fifty_distinct_verified_targets():
    from scripts.evaluate_retrieval import QUESTIONS

    cases = read_questions(QUESTIONS)
    assert len(cases) == 50
    assert len({case["id"] for case in cases}) == 50
    assert all(case["anchor"] for case in cases)


def test_page_and_section_need_the_right_source():
    page_case = {"source": "manual.pdf", "page": 4, "section": ""}
    section_case = {"source": "rules.xml", "page": None, "section": "229.307"}
    rows = [
        {"source": "other.pdf", "page": 4, "section": None},
        {"source": "manual.pdf", "page": 3, "section": None},
        {"source": "manual.pdf", "page": 4, "section": None},
    ]
    assert rank_of(rows, page_case) == 3
    assert rank_of(rows, section_case) is None
    assert rank_of([{"source": "rules.xml", "page": None, "section": "229.307"}], section_case) == 1


def test_scoring_counts_source_and_exact_location_separately():
    cases = [{
        "id": "1", "question": "How?", "source": "manual.pdf",
        "page": 4, "section": "", "anchor": "An answer",
    }]
    rows = [
        {"source": "manual.pdf", "page": 3, "section": None},
        {"source": "other.pdf", "page": 4, "section": None},
        {"source": "manual.pdf", "page": 4, "section": None},
    ]
    report = score_cases(cases, lambda question, limit: rows)
    assert report["source_hits"] == {"1": 1, "5": 1, "10": 1}
    assert report["location_hits"] == {"1": 0, "5": 1, "10": 1}


def test_anchor_checks_the_passage_not_only_the_page_label():
    class FakeConnection:
        def execute(self, query, params):
            assert params == ("manual.pdf", 4)
            return self

        def fetchall(self):
            return [("The relevant fact\nis on this page.",)]

    case = {"id": "1", "source": "manual.pdf", "page": 4,
            "section": "", "anchor": "relevant fact is not on this page"}
    with pytest.raises(ValueError, match="Question 1"):
        check_anchor(FakeConnection(), case)
    case["anchor"] = "relevant fact is on this page."
    # A newline in the PDF text is fine, but missing words are not.
    check_anchor(FakeConnection(), case)


def test_question_file_rejects_two_locations(tmp_path):
    path = tmp_path / "cases.tsv"
    path.write_text(
        "id\tquestion\tsource\tpage\tsection\tanchor\n"
        "1\tWhat?\trules.xml\t3\t229.307\tKnown answer\n",
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="needs a page or section"):
        read_questions(path)
