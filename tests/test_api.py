"""Tests for api/main.py, through real HTTP requests to the app.

The routes that refuse bad input before touching the database run anywhere,
CI included: the connection and the signed in person are replaced with stand
ins. The full journey of signing in, upload, history, inspector and approval
needs PostgreSQL and is skipped without it. Every account and file name a
test creates starts with zz_ and is removed afterwards.
"""

import time
from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient

from finlint import auth
from finlint.api import main
from finlint.api.main import app, current_user, db

WORKBOOK = open("tests/fixtures/circular.xlsx", "rb").read()
PASSWORD = "zz-test-password-1"

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


@pytest.fixture(autouse=True)
def fresh_limits():
    """Rate limit counts from one test must never refuse a request in the next."""
    main.limiter.reset()
    yield
    main.limiter.reset()
    app.dependency_overrides.clear()


@pytest.fixture
def client(tmp_path, monkeypatch):
    """The app, with uploads written to a temporary folder."""
    monkeypatch.setenv("FINLINT_UPLOADS", str(tmp_path))
    return TestClient(app)


def stand_in(client, role="reviewer"):
    """No database, and a signed in person of this role.

    The cookie is a placeholder: the early upload guard only checks that one
    is present, and current_user, which would check it, is replaced.
    """
    def no_connection():
        yield None
    app.dependency_overrides[db] = no_connection
    app.dependency_overrides[current_user] = lambda: auth.User(0, f"zz_{role}", role)
    client.cookies.set(main.SESSION_COOKIE, "stand-in")


@pytest.fixture
def no_db(client):
    stand_in(client)


def upload(client, data, name):
    return client.post("/api/check", files={"file": (name, data, "application/octet-stream")})


def a_finding(**changes):
    finding = {"rule_id": "r", "severity": "low", "sheet": "S", "coordinate": "A1", "message": "m"}
    return {**finding, **changes}


# --- runs anywhere -------------------------------------------------------------

def test_health_always_answers(client):
    """The page decides live or sample from this, so it must never fail, and
    it needs no account."""
    body = client.get("/api/health").json()

    assert body["ok"] is True
    assert set(body) == {"ok", "database", "llm", "version"}


def test_health_answers_quickly_when_the_database_is_down(client, monkeypatch):
    """libpq waits about two seconds per address, and the page gives up at
    four. Health must say "database off", not leave the page guessing."""
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


def test_evaluation_is_served(client, no_db):
    response = client.get("/api/evaluation")

    assert response.status_code == 200
    assert {"tiers", "retrieval"} <= set(response.json())


def test_a_missing_evaluation_file_is_not_found(client, no_db, monkeypatch, tmp_path):
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

    response = client.post("/api/explain", json={"file": "model.xlsx", "finding": a_finding()})

    assert response.status_code == 503
    assert "GROQ_API_KEY" in response.json()["detail"]


def test_a_malformed_finding_is_refused(client, no_db):
    """Pydantic checks the shape, so a bad severity never reaches the agent."""
    response = client.post("/api/explain",
                           json={"file": "model.xlsx", "finding": a_finding(severity="catastrophic")})

    assert response.status_code == 422


# --- roles: who may do what ------------------------------------------------------

def test_a_signer_cannot_upload(client):
    stand_in(client, "signer")

    response = upload(client, WORKBOOK, "model.xlsx")

    assert response.status_code == 403
    assert "signer cannot upload" in response.json()["detail"]


def test_an_analyst_cannot_mark_a_finding_as_intentional(client):
    """Segregation of duties: whoever built the model does not sign it off."""
    stand_in(client, "analyst")

    response = client.post("/api/approvals",
                           json={"file": "model.xlsx", "finding": a_finding(), "reason": "why"})

    assert response.status_code == 403
    assert "analyst cannot mark findings as intentional" in response.json()["detail"]


# --- rate limits ------------------------------------------------------------------

def test_too_many_uploads_are_refused_with_a_wait(client, no_db, monkeypatch):
    monkeypatch.setattr(main, "UPLOAD_LIMIT", (2, 60))

    answers = [upload(client, b"hello", "notes.txt").status_code for _ in range(3)]

    assert answers == [400, 400, 429]


def test_a_refusal_says_how_long_to_wait(client, no_db, monkeypatch):
    monkeypatch.setattr(main, "UPLOAD_LIMIT", (1, 60))
    upload(client, b"hello", "notes.txt")

    response = upload(client, b"hello", "notes.txt")

    assert response.status_code == 429
    assert 0 < int(response.headers["Retry-After"]) <= 60
    assert "Try again in" in response.json()["detail"]


def test_too_many_standards_questions_are_refused(client, no_db, monkeypatch):
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    monkeypatch.setenv("GROQ_API_KEY", "zz-not-a-real-key")
    monkeypatch.setattr(main, "EXPLAIN_LIMIT", (0, 60))

    response = client.post("/api/explain", json={"file": "model.xlsx", "finding": a_finding()})

    assert response.status_code == 429
    assert "standards questions" in response.json()["detail"]


def test_an_anonymous_upload_is_refused_before_it_is_read(client):
    """FastAPI reads the whole body before any route check runs. Review sent a
    400 MB upload with no cookie and the server took it all in first."""
    response = upload(client, WORKBOOK, "model.xlsx")

    assert response.status_code == 401


def test_an_oversized_upload_is_refused_from_its_declared_size(client):
    client.cookies.set(main.SESSION_COOKIE, "anything")

    response = client.post("/api/check", content=b"x",
                           headers={"Content-Length": str(main.UPLOAD_BODY_LIMIT + 1),
                                    "Content-Type": "multipart/form-data; boundary=x"})

    assert response.status_code == 413
    assert "larger than" in response.json()["detail"]


def test_a_post_from_another_website_is_refused(client, no_db):
    """Stops another site using a signed in person's cookie to act for them."""
    response = client.post("/api/approvals", headers={"Origin": "https://evil.example"},
                           json={"file": "model.xlsx", "finding": a_finding(), "reason": "why"})

    assert response.status_code == 403
    assert "another website" in response.json()["detail"]


def test_the_development_page_may_post(client, no_db):
    response = client.post("/api/auth/login", headers={"Origin": "http://localhost:3000"},
                           json={"username": "x" * 65, "password": "p"})

    # Past the origin check, and refused only for the over long name.
    assert response.status_code == 422


def test_every_address_has_a_ceiling(client, monkeypatch):
    monkeypatch.setattr(main, "API_LIMIT", (3, 60))

    answers = [client.get("/api/health").status_code for _ in range(4)]

    assert answers == [200, 200, 200, 429]


# --- the full journey, against PostgreSQL ------------------------------------

def _delete_file_rows(conn, name):
    with conn.cursor() as cur:
        cur.execute("SELECT id FROM files WHERE name = %s", (name,))
        row = cur.fetchone()
        if row:
            cur.execute("DELETE FROM findings WHERE run_id IN "
                        "(SELECT id FROM runs WHERE file_id = %s)", (row[0],))
            cur.execute("DELETE FROM approvals WHERE file_id = %s", (row[0],))
            cur.execute("DELETE FROM runs WHERE file_id = %s", (row[0],))
            cur.execute("DELETE FROM files WHERE id = %s", (row[0],))


@pytest.fixture
def accounts():
    """Make zz_ accounts on demand; every one, and its sessions, is removed after."""
    from finlint.rag.store import connect

    main.ensure_schema()
    conn = connect()
    made = []

    def make(role):
        name = f"zz_{role}_{len(made)}_{int(time.time() * 1000) % 10**9}"
        made.append(auth.create_user(conn, name, role, PASSWORD))
        return made[-1]

    yield make

    with conn.cursor() as cur:
        for user in made:
            cur.execute("DELETE FROM users WHERE id = %s", (user.id,))
    conn.commit()
    conn.close()


@pytest.fixture
def signed_in(client, accounts):
    """A client signed in as a fresh account of the role asked for."""
    def sign_in(role="reviewer"):
        user = accounts(role)
        response = client.post("/api/auth/login", json={"username": user.username, "password": PASSWORD})
        assert response.status_code == 200, response.text
        return user
    return sign_in


@pytest.fixture
def checked_name():
    """A unique workbook name, with every row it creates removed afterwards."""
    from finlint.rag.store import connect

    name = f"zz_api_{datetime.now(timezone.utc).timestamp()}.xlsx"
    yield name

    conn = connect()
    try:
        _delete_file_rows(conn, name)
        conn.commit()
    finally:
        conn.close()


@needs_db
def test_nothing_is_readable_without_signing_in(client):
    for path in ("/api/files", "/api/evaluation", "/api/files/x.xlsx/run", "/api/auth/me"):
        response = client.get(path)
        assert response.status_code == 401, path
        assert "Sign in" in response.json()["detail"] or "No accounts" in response.json()["detail"]


@needs_db
def test_signing_in_returns_the_role_and_what_it_allows(client, accounts):
    user = accounts("analyst")

    response = client.post("/api/auth/login", json={"username": user.username.upper(), "password": PASSWORD})

    assert response.status_code == 200
    assert response.json() == {"username": user.username, "role": "analyst",
                               "can_upload": True, "can_decide": False}
    cookie = response.headers["set-cookie"].lower()
    assert "httponly" in cookie and "samesite=lax" in cookie
    assert client.get("/api/auth/me").json()["username"] == user.username


@needs_db
def test_a_wrong_password_is_refused_without_saying_which_part_was_wrong(client, accounts):
    user = accounts("analyst")

    wrong_password = client.post("/api/auth/login", json={"username": user.username, "password": "nope-nope-nope"})
    wrong_name = client.post("/api/auth/login", json={"username": "zz_nobody_at_all", "password": PASSWORD})

    assert wrong_password.status_code == wrong_name.status_code == 401
    assert wrong_password.json() == wrong_name.json()


@needs_db
def test_guessing_passwords_is_stopped_after_five_tries(client, accounts):
    user = accounts("analyst")
    for _ in range(5):
        client.post("/api/auth/login", json={"username": user.username, "password": "guess-guess-guess"})

    # Even the right password is refused until the window passes.
    response = client.post("/api/auth/login", json={"username": user.username, "password": PASSWORD})

    assert response.status_code == 429
    assert "Too many wrong passwords" in response.json()["detail"]


@needs_db
def test_signing_out_ends_the_session_everywhere(client, signed_in):
    signed_in("reviewer")
    token = client.cookies.get(main.SESSION_COOKIE)

    client.post("/api/auth/logout")

    # The old token is dead on the server, not just forgotten by this browser.
    client.cookies.set(main.SESSION_COOKIE, token)
    assert client.get("/api/files").status_code == 401


@needs_db
def test_an_upload_is_checked_and_becomes_version_one(client, signed_in, checked_name):
    signed_in("analyst")

    response = upload(client, WORKBOOK, checked_name)

    assert response.status_code == 200
    run = response.json()
    assert set(run) == RUN_KEYS
    assert run["file"] == checked_name
    assert run["version"] == 1
    assert run["findings"], "the circular fixture has at least one finding"
    assert all(f["status"] == "new" for f in run["findings"])


@needs_db
def test_the_same_file_twice_is_version_two_and_unchanged(client, signed_in, checked_name):
    signed_in("analyst")
    upload(client, WORKBOOK, checked_name)
    run = upload(client, WORKBOOK, checked_name).json()

    assert run["version"] == 2
    assert run["previous_version"] == 1
    assert run["unchanged_since_previous"] is True
    assert all(f["status"] == "still_there" for f in run["findings"])

    history = client.get(f"/api/files/{checked_name}/history").json()
    assert [h["version"] for h in history] == [1, 2]


@needs_db
def test_a_checked_file_is_listed_and_can_be_read_back(client, signed_in, checked_name):
    signed_in("analyst")
    first = upload(client, WORKBOOK, checked_name).json()

    listed = {f["name"] for f in client.get("/api/files").json()}
    again = client.get(f"/api/files/{checked_name}/run").json()

    assert checked_name in listed
    assert again["run_id"] == first["run_id"]


@needs_db
def test_the_inspector_opens_a_flagged_cell(client, signed_in, checked_name):
    signed_in("analyst")
    finding = upload(client, WORKBOOK, checked_name).json()["findings"][0]
    ref = f"{finding['sheet']}!{finding['coordinate']}"

    cell = client.get(f"/api/files/{checked_name}/cell", params={"ref": ref}).json()

    assert cell["ref"] == ref


@needs_db
def test_an_unknown_file_is_not_found(client, signed_in):
    signed_in("signer")

    response = client.get("/api/files/zz_never_checked.xlsx/run")

    assert response.status_code == 404
    assert "has not been checked" in response.json()["detail"]


def _sendable(finding):
    return {k: finding[k] for k in ("rule_id", "severity", "sheet", "coordinate", "message")}


@needs_db
def test_an_approval_is_recorded_under_the_account_signed_in(client, signed_in, checked_name):
    """The name typed in the request is ignored: nobody can decide as somebody else."""
    reviewer = signed_in("reviewer")
    finding = upload(client, WORKBOOK, checked_name).json()["findings"][0]

    response = client.post("/api/approvals", json={
        "file": checked_name, "finding": _sendable(finding),
        "reason": "  Deliberate input  ", "who": "somebody else"})

    assert response.status_code == 200
    assert response.json()["reason"] == "Deliberate input"
    assert response.json()["decided_by"] == reviewer.username
    run = client.get(f"/api/files/{checked_name}/run").json()
    assert run["findings"][0]["approved"] is True
    assert len(client.get(f"/api/files/{checked_name}/approvals").json()) == 1


@needs_db
def test_an_approval_without_a_reason_is_refused(client, signed_in, checked_name):
    signed_in("reviewer")
    finding = upload(client, WORKBOOK, checked_name).json()["findings"][0]

    response = client.post("/api/approvals", json={
        "file": checked_name, "finding": _sendable(finding), "reason": "  "})

    assert response.status_code == 400
    assert "reason" in response.json()["detail"]


@needs_db
def test_a_finding_never_reported_cannot_be_approved(client, signed_in, checked_name):
    """Otherwise a caller could silence a cell before it was ever flagged."""
    signed_in("reviewer")
    upload(client, WORKBOOK, checked_name)
    invented = a_finding(rule_id="hardcoded_value", sheet="Nowhere", coordinate="Z99")

    response = client.post("/api/approvals", json={
        "file": checked_name, "finding": invented, "reason": "why"})

    assert response.status_code == 400
