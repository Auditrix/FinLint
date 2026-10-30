"""Tests for auth.py (passwords, accounts, sessions) and ratelimit.py."""

import pytest

from finlint import auth
from finlint.ratelimit import RateLimiter


# --- passwords: run anywhere ------------------------------------------------------

def test_the_right_password_matches_its_hash():
    stored = auth.hash_password("correct horse battery")

    assert auth.verify_password("correct horse battery", stored)
    assert not auth.verify_password("correct horse batterY", stored)


def test_the_password_itself_is_never_stored():
    stored = auth.hash_password("correct horse battery")

    assert "correct horse battery" not in stored
    assert stored.startswith("scrypt$")


def test_the_same_password_hashes_differently_each_time():
    """A random salt, so two people with one password do not share a hash."""
    assert auth.hash_password("same password!") != auth.hash_password("same password!")


@pytest.mark.parametrize("stored", ["", "nonsense", "md5$abc", "scrypt$1$2$3$zz$zz"])
def test_a_damaged_hash_never_matches(stored):
    assert not auth.verify_password("anything at all", stored)


def test_roles_decide_what_the_page_offers():
    assert auth.User(1, "a", "analyst").public() == {
        "username": "a", "role": "analyst", "can_upload": True, "can_decide": False}
    assert auth.User(2, "r", "reviewer").public()["can_decide"] is True
    assert auth.User(3, "s", "signer").public()["can_upload"] is False


# --- rate limiter: run anywhere, on a fake clock ------------------------------------

class Clock:
    def __init__(self):
        self.now = 1000.0

    def __call__(self):
        return self.now


def test_requests_inside_the_limit_pass_and_the_next_waits():
    clock = Clock()
    limiter = RateLimiter(clock)

    assert [limiter.hit("k", 3, 60) for _ in range(3)] == [0, 0, 0]
    assert limiter.hit("k", 3, 60) == pytest.approx(60)


def test_the_window_slides():
    clock = Clock()
    limiter = RateLimiter(clock)
    limiter.hit("k", 1, 60)

    clock.now += 30
    assert limiter.hit("k", 1, 60) == pytest.approx(30)
    clock.now += 31
    assert limiter.hit("k", 1, 60) == 0


def test_a_refused_request_does_not_extend_the_wait():
    clock = Clock()
    limiter = RateLimiter(clock)
    limiter.hit("k", 1, 60)
    for _ in range(10):
        limiter.hit("k", 1, 60)

    clock.now += 61
    assert limiter.hit("k", 1, 60) == 0


def test_keys_are_counted_separately():
    limiter = RateLimiter(Clock())
    limiter.hit("nara", 1, 60)

    assert limiter.hit("sowb", 1, 60) == 0


def test_wait_needed_counts_nothing_and_creates_nothing():
    """Asking used to create an entry, so a flood of new names grew memory."""
    limiter = RateLimiter(Clock())

    assert limiter.wait_needed("k", 1, 60) == 0
    assert limiter.wait_needed("k", 1, 60) == 0
    assert limiter.size() == 0
    limiter.hit("k", 1, 60)
    assert limiter.wait_needed("k", 1, 60) > 0
    limiter.clear("k")
    assert limiter.wait_needed("k", 1, 60) == 0


def test_hit_all_counts_every_key_or_none():
    limiter = RateLimiter(Clock())
    limiter.hit("busy", 1, 60)

    assert limiter.hit_all([("free", 5, 60), ("busy", 1, 60)]) > 0
    # Refused as a whole, so "free" was not counted either.
    assert limiter.wait_needed("free", 1, 60) == 0


def test_a_burst_from_many_threads_never_exceeds_the_limit():
    """Checking and counting were separate steps, so simultaneous password
    guesses all passed the check: 24 got through a limit of 5 in review."""
    import threading

    limiter = RateLimiter()
    allowed = []
    lock = threading.Lock()
    start = threading.Barrier(40)

    def guess():
        start.wait()
        if limiter.hit_all([("name", 5, 60), ("address", 20, 60)]) == 0:
            with lock:
                allowed.append(1)

    workers = [threading.Thread(target=guess) for _ in range(40)]
    for w in workers:
        w.start()
    for w in workers:
        w.join()

    assert len(allowed) == 5


def test_undo_gives_back_the_last_hit():
    limiter = RateLimiter(Clock())
    limiter.hit("k", 1, 60)

    limiter.undo("k")

    assert limiter.hit("k", 1, 60) == 0


def test_idle_keys_are_swept_out_of_memory():
    """Review found 15,000 old addresses still held an hour later."""
    from finlint import ratelimit

    clock = Clock()
    limiter = RateLimiter(clock)
    for n in range(ratelimit.SWEEP_EVERY - 1):
        limiter.hit(f"address {n}", 10, 60)
    assert limiter.size() == ratelimit.SWEEP_EVERY - 1

    clock.now += 3600
    limiter.hit("one more", 10, 60)

    assert limiter.size() <= 1


# --- accounts and sessions: need PostgreSQL ------------------------------------------

def _database_available():
    try:
        from finlint.rag.store import connect
        connect().close()
        return True
    except Exception:
        return False


needs_db = pytest.mark.skipif(not _database_available(), reason="no reachable PostgreSQL")


@pytest.fixture
def conn():
    from finlint.api.main import ensure_schema
    from finlint.rag.store import connect

    ensure_schema()
    connection = connect()
    yield connection
    with connection.cursor() as cur:
        cur.execute("DELETE FROM users WHERE username LIKE 'zz\\_auth\\_%'")
    connection.commit()
    connection.close()


@needs_db
def test_an_account_can_sign_in_and_hold_a_session(conn):
    user = auth.create_user(conn, "zz_auth_nara", "reviewer", "a long password")

    assert auth.authenticate(conn, "ZZ_AUTH_NARA", "a long password") == user
    token = auth.start_session(conn, user)
    assert auth.user_for_token(conn, token) == user

    auth.end_session(conn, token)
    assert auth.user_for_token(conn, token) is None


@needs_db
def test_only_the_hash_of_a_session_token_is_stored(conn):
    user = auth.create_user(conn, "zz_auth_token", "signer", "a long password")
    token = auth.start_session(conn, user)

    with conn.cursor() as cur:
        cur.execute("SELECT token_hash FROM sessions WHERE user_id = %s", (user.id,))
        stored = cur.fetchone()[0]
    assert stored != token


@needs_db
def test_an_expired_session_is_refused(conn):
    user = auth.create_user(conn, "zz_auth_old", "analyst", "a long password")
    token = auth.start_session(conn, user)
    with conn.cursor() as cur:
        cur.execute("UPDATE sessions SET expires_at = now() - interval '1 minute' WHERE user_id = %s", (user.id,))
    conn.commit()

    assert auth.user_for_token(conn, token) is None


@needs_db
def test_a_disabled_account_cannot_sign_in_or_keep_its_session(conn):
    user = auth.create_user(conn, "zz_auth_gone", "analyst", "a long password")
    token = auth.start_session(conn, user)
    with conn.cursor() as cur:
        cur.execute("UPDATE users SET disabled = true WHERE id = %s", (user.id,))
    conn.commit()

    assert auth.authenticate(conn, "zz_auth_gone", "a long password") is None
    assert auth.user_for_token(conn, token) is None


@needs_db
@pytest.mark.parametrize("name, role, password, message", [
    ("zz_auth_short", "analyst", "short", "at least"),
    ("zz_auth_role", "admin", "a long password", "role must be"),
    ("x", "analyst", "a long password", "3 to 32"),
    ("zz auth space", "analyst", "a long password", "3 to 32"),
])
def test_bad_accounts_are_refused_with_a_reason(conn, name, role, password, message):
    with pytest.raises(ValueError, match=message):
        auth.create_user(conn, name, role, password)


@needs_db
def test_a_name_can_only_be_taken_once(conn):
    auth.create_user(conn, "zz_auth_twice", "analyst", "a long password")

    with pytest.raises(ValueError, match="already an account"):
        auth.create_user(conn, "ZZ_Auth_Twice", "reviewer", "another long one")


def test_a_limit_of_zero_refuses_everything_for_the_whole_window():
    """Used to crash with an IndexError: there was no earliest hit to wait out."""
    limiter = RateLimiter(Clock())

    assert limiter.hit("k", 0, 60) == 60
    assert limiter.wait_needed("k", 0, 60) == 60
