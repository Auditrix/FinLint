"""Tests for storage.py, where every uploaded workbook is kept."""

import hashlib

import pytest

from finlint import storage
from finlint.storage import RejectedUpload, path_for, safe_name, store

WORKBOOK = open("tests/fixtures/circular.xlsx", "rb").read()


@pytest.fixture(autouse=True)
def uploads(tmp_path, monkeypatch):
    """Every test writes to its own empty folder, never to data/uploads."""
    monkeypatch.setenv("FINLINT_UPLOADS", str(tmp_path))
    return tmp_path


# --- safe_name: the only part of a file name that is trusted -----------------

@pytest.mark.parametrize("sent, kept", [
    ("model.xlsx", "model.xlsx"),
    ("Q4 Forecast.XLSM", "Q4 Forecast.XLSM"),
    ("../../etc/model.xlsx", "model.xlsx"),
    ("C:\\Users\\nara\\model.xlsx", "model.xlsx"),
])
def test_a_path_is_reduced_to_its_last_part(sent, kept):
    """A crafted name can never point outside its own folder."""
    assert safe_name(sent) == kept


@pytest.mark.parametrize("sent", [None, "", "   ", ".xlsx", "notes.txt", "model.xls", "dir/"])
def test_names_that_are_not_workbooks_are_refused(sent):
    with pytest.raises(RejectedUpload):
        safe_name(sent)


@pytest.mark.parametrize("sent", ["C:model.xlsx", "q?.xlsx", "a*b.xlsx", "a|b.xlsx", 'a"b.xlsx', "tab\tname.xlsx"])
def test_characters_a_file_name_cannot_have_are_refused(sent):
    """On Windows "C:model.xlsx" pointed outside the uploads folder, and the
    API checked whatever file sat there instead of the upload. Found in review."""
    with pytest.raises(RejectedUpload):
        safe_name(sent)


# --- store --------------------------------------------------------------------

def test_a_workbook_is_stored_under_its_hash_and_name(uploads):
    path = store(WORKBOOK, "model.xlsx")

    assert path == uploads / hashlib.sha256(WORKBOOK).hexdigest() / "model.xlsx"
    assert path.read_bytes() == WORKBOOK


def test_the_same_bytes_twice_are_stored_once(uploads):
    first = store(WORKBOOK, "model.xlsx")
    second = store(WORKBOOK, "model.xlsx")

    assert first == second
    assert len(list(uploads.iterdir())) == 1


def test_a_changed_workbook_keeps_the_old_version(uploads):
    """Every version is kept, so an old run can still be inspected."""
    old = store(WORKBOOK, "model.xlsx")
    new = store(WORKBOOK + b"changed", "model.xlsx")

    assert old != new
    assert old.exists() and new.exists()


def test_no_temporary_file_is_left_behind(uploads):
    path = store(WORKBOOK, "model.xlsx")

    assert [p.name for p in path.parent.iterdir()] == ["model.xlsx"]


def test_the_same_upload_at_once_from_many_threads_all_succeed(uploads):
    """A double click sends the same file twice at once. Both used to write to
    one shared temporary file, and about a third of them failed."""
    import threading

    paths, errors = [], []

    def upload():
        try:
            paths.append(store(WORKBOOK, "model.xlsx"))
        except Exception as error:
            errors.append(error)

    for _ in range(5):
        workers = [threading.Thread(target=upload) for _ in range(4)]
        for w in workers:
            w.start()
        for w in workers:
            w.join()

    assert errors == []
    assert len(set(paths)) == 1
    assert [p.name for p in paths[0].parent.iterdir()] == ["model.xlsx"]


def test_an_empty_upload_is_refused(uploads):
    with pytest.raises(RejectedUpload, match="empty"):
        store(b"", "model.xlsx")
    assert list(uploads.iterdir()) == []


def test_an_oversized_upload_is_refused(uploads, monkeypatch):
    monkeypatch.setattr(storage, "MAX_BYTES", 10)

    with pytest.raises(RejectedUpload, match="larger than"):
        store(b"x" * 11, "model.xlsx")
    assert list(uploads.iterdir()) == []


def test_path_for_finds_what_store_wrote():
    path = store(WORKBOOK, "model.xlsx")

    assert path_for(hashlib.sha256(WORKBOOK).hexdigest(), "model.xlsx") == path
