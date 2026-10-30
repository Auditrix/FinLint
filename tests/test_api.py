"""Tests for api/main.py, through real HTTP requests to the app.

The routes that refuse bad input before touching the database run anywhere,
CI included: the connection is replaced with a stand in. The full journey of
upload, history, inspector and approval needs PostgreSQL and is skipped
without it. Every file name a test creates starts with zz_ and is removed
afterwards.
"""

from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient

from finlint.api import main
from finlint.api.main import app, db

WORKBOOK = open("tests/fixtures/circular.xlsx", "rb").read()

# Every key the frontend reads from a run. A missing one fails silently there.
RUN_KEYS = {
    "file", "run_id", "version", "previous_version", "created_at", "sha256",
    "unchanged_since_previous", "score", "stats", "findings", "resolved",
}


def _database_available():
    try:
        from finlint.rag.store import connect
        connect().close()
        return True
    except Exception:
        return False


needs_db = pytest.mark.skipif(not _database_available(), reason="no reachable PostgreSQL")


@pytest.fixture
def client(tmp_path, monkeypatch):
    """The app, with uploads written to a temporary folder."""
    monkeypatch.setenv("FINLINT_UPLOADS", str(tmp_path))
    return TestClient(app)


@pytest.fixture
def no_db():
    """Replace the connection for routes that must refuse before using it."""
    def stand_in():
        yield None
    app.dependency_overrides[db] = stand_in
    yield
    app.dependency_overrides.clear()


def upload(client, data, name):
    return client.post("/api/check", files={"file": (name, data, "application/octet-stream")})


# --- runs anywhere -------------------------------------------------------------

def test_health_always_answers(client):
    """The page decides live or sample from this, so it must never fail."""
    body = client.get("/api/health").json()

    assert body["ok"] is True
    assert set(body) == {"ok", "database", "llm", "version"}


def test_health_answers_quickly_when_the_database_is_down(client, monkeypatch):
    """libpq waits about two seconds per address, and the page gives up at
    four. Health must say "database off", not leave the page guessing."""
    import time

    monkeypatch.setattr(main, "DATABASE_URL", "postgresql://x:x@localhost:1/x")

    started = time.perf_counter()
    body = client.get("/api/health").json()

    assert body["database"] is False
    assert time.perf_counter() - started < 2


def test_an_unknown_api_path_answers_json(client):
    """Not the website's HTML 404 page, which the frontend cannot read."""
    response = client.get("/api/no-such-thing")

    assert response.status_code == 404
    assert "no API endpoint" in response.json()["detail"]


def test_a_missing_database_address_is_a_clear_error(monkeypatch):
    """psycopg.connect(None) raised AttributeError, which became a 500."""
    import psycopg

    from finlint.rag import store

    monkeypatch.setattr(store, "DATABASE_URL", None)

    with pytest.raises(psycopg.OperationalError, match="DATABASE_URL is not set"):
        store.connect()


def test_evaluation_is_served(client):
    response = client.get("/api/evaluation")

    assert response.status_code == 200
    assert {"tiers", "retrieval"} <= set(response.json())


def test_a_missing_evaluation_file_is_not_found(client, monkeypatch, tmp_path):
    monkeypatch.setattr(main, "EVALUATION", tmp_path / "missing.json")

    response = client.get("/api/evaluation")

    assert response.status_code == 404
    assert "missing" in response.json()["detail"]


def test_a_file_that_is_not_a_workbook_is_refused(client, no_db):
    response = upload(client, b"hello", "notes.txt")

    assert response.status_code == 400
    assert "not an Excel workbook" in response.json()["detail"]


def test_an_empty_upload_is_refused(client, no_db):
    response = upload(client, b"", "model.xlsx")

    assert response.status_code == 400
    assert "empty" in response.json()["detail"]


def test_an_unreadable_workbook_is_refused_and_not_kept(client, no_db, tmp_path):
    """Bytes named .xlsx that are not a workbook: a clear 400, nothing stored."""
    response = upload(client, b"this is not a zip file", "broken.xlsx")

    assert response.status_code == 400
    assert "could not be read" in response.json()["detail"]
    assert list(tmp_path.iterdir()) == []


def test_a_cell_reference_needs_a_sheet(client, no_db):
    response = client.get("/api/files/model.xlsx/cell", params={"ref": "A1"})

    assert response.status_code == 400
    assert "Sheet!A1" in response.json()["detail"]


def test_explain_says_when_no_model_is_configured(client, no_db, monkeypatch):
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    finding = {"rule_id": "r", "severity": "low", "sheet": "S", "coordinate": "A1", "message": "m"}

    response = client.post("/api/explain", json={"file": "model.xlsx", "finding": finding})

    assert response.status_code == 503
    assert "GROQ_API_KEY" in response.json()["detail"]


def test_a_malformed_finding_is_refused(client, no_db):
    """Pydantic checks the shape, so a bad severity never reaches the agent."""
    finding = {"rule_id": "r", "severity": "catastrophic", "sheet": "S", "coordinate": "A1", "message": "m"}

    response = client.post("/api/explain", json={"file": "model.xlsx", "finding": finding})

    assert response.status_code == 422


# --- the full journey, against PostgreSQL ------------------------------------

@pytest.fixture
def checked_name():
    """A unique workbook name, with every row it creates removed afterwards."""
    from finlint.rag.store import connect

    name = f"zz_api_{datetime.now(timezone.utc).timestamp()}.xlsx"
    yield name

    conn = connect()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT id FROM files WHERE name = %s", (name,))
            row = cur.fetchone()
            if row:
                cur.execute("DELETE FROM findings WHERE run_id IN "
                            "(SELECT id FROM runs WHERE file_id = %s)", (row[0],))
                cur.execute("DELETE FROM approvals WHERE file_id = %s", (row[0],))
                cur.execute("DELETE FROM runs WHERE file_id = %s", (row[0],))
                cur.execute("DELETE FROM files WHERE id = %s", (row[0],))
        conn.commit()
    finally:
        conn.close()


@needs_db
def test_an_upload_is_checked_and_becomes_version_one(client, checked_name):
    response = upload(client, WORKBOOK, checked_name)

    assert response.status_code == 200
    run = response.json()
    assert set(run) == RUN_KEYS
    assert run["file"] == checked_name
    assert run["version"] == 1
    assert run["findings"], "the circular fixture has at least one finding"
    assert all(f["status"] == "new" for f in run["findings"])


@needs_db
def test_the_same_file_twice_is_version_two_and_unchanged(client, checked_name):
    upload(client, WORKBOOK, checked_name)
    run = upload(client, WORKBOOK, checked_name).json()

    assert run["version"] == 2
    assert run["previous_version"] == 1
    assert run["unchanged_since_previous"] is True
    assert all(f["status"] == "still_there" for f in run["findings"])

    history = client.get(f"/api/files/{checked_name}/history").json()
    assert [h["version"] for h in history] == [1, 2]


@needs_db
def test_a_checked_file_is_listed_and_can_be_read_back(client, checked_name):
    first = upload(client, WORKBOOK, checked_name).json()

    listed = {f["name"] for f in client.get("/api/files").json()}
    again = client.get(f"/api/files/{checked_name}/run").json()

    assert checked_name in listed
    assert again["run_id"] == first["run_id"]


@needs_db
def test_the_inspector_opens_a_flagged_cell(client, checked_name):
    finding = upload(client, WORKBOOK, checked_name).json()["findings"][0]
    ref = f"{finding['sheet']}!{finding['coordinate']}"

    cell = client.get(f"/api/files/{checked_name}/cell", params={"ref": ref}).json()

    assert cell["ref"] == ref


@needs_db
def test_an_unknown_file_is_not_found(client):
    response = client.get("/api/files/zz_never_checked.xlsx/run")

    assert response.status_code == 404
    assert "has not been checked" in response.json()["detail"]


@needs_db
def test_an_approval_is_recorded_and_greys_the_finding(client, checked_name):
    finding = upload(client, WORKBOOK, checked_name).json()["findings"][0]
    sent = {k: finding[k] for k in ("rule_id", "severity", "sheet", "coordinate", "message")}

    response = client.post("/api/approvals", json={
        "file": checked_name, "finding": sent, "reason": "Deliberate input", "who": "nara"})

    assert response.status_code == 200
    assert response.json()["reason"] == "Deliberate input"
    assert response.json()["decided_by"] == "nara"
    run = client.get(f"/api/files/{checked_name}/run").json()
    assert run["findings"][0]["approved"] is True
    assert len(client.get(f"/api/files/{checked_name}/approvals").json()) == 1


@needs_db
def test_an_approval_without_a_reason_is_refused(client, checked_name):
    finding = upload(client, WORKBOOK, checked_name).json()["findings"][0]
    sent = {k: finding[k] for k in ("rule_id", "severity", "sheet", "coordinate", "message")}

    response = client.post("/api/approvals", json={
        "file": checked_name, "finding": sent, "reason": "  ", "who": "nara"})

    assert response.status_code == 400
    assert "reason" in response.json()["detail"]


@needs_db
def test_a_finding_never_reported_cannot_be_approved(client, checked_name):
    """Otherwise a caller could silence a cell before it was ever flagged."""
    upload(client, WORKBOOK, checked_name)
    invented = {"rule_id": "hardcoded_value", "severity": "low",
                "sheet": "Nowhere", "coordinate": "Z99", "message": "m"}

    response = client.post("/api/approvals", json={
        "file": checked_name, "finding": invented, "reason": "why", "who": "nara"})

    assert response.status_code == 400
