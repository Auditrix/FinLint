"""Who is using FinLint, and what they are allowed to do.

Three roles, one per persona in CLAUDE.md Section 3:

- analyst   builds the model with AI help. Uploads, reads findings, asks for a
            supporting standard. Cannot accept a finding as intentional.
- reviewer  everything an analyst can, plus "Mark as intentional".
- signer    reads findings, history and the audit log. Changes nothing.

The analyst cannot accept findings on purpose. That is segregation of duties
(Section 13): whoever builds the work must not be the one who signs it off.

Passwords are never stored. Each is turned into a scrypt hash: a slow, salted,
one way scramble from Python's own hashlib, so no extra package is needed and
a stolen table cannot be reversed into passwords. A session is a random token
in a cookie; only the token's SHA-256 is stored, so the sessions table is no
use to anyone who reads it.

Accounts are created with scripts/create_user.py. There is no sign up page:
in a finance team, someone responsible decides who gets access.
"""

import hashlib
import hmac
import re
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

import psycopg

ROLES = ("analyst", "reviewer", "signer")

# Who may do what. The API checks these, and the page reads the same rules from
# /api/auth/me so it can grey out what a role cannot do.
CAN_UPLOAD = ("analyst", "reviewer")
CAN_DECIDE = ("reviewer",)

# A working day. After that the person signs in again.
SESSION_HOURS = 12

MIN_PASSWORD = 10
USERNAME = re.compile(r"^[a-z0-9][a-z0-9._-]{2,31}$")

# scrypt cost settings: about 50 ms per check on a laptop, which is nothing for
# a person signing in and a great deal for someone guessing millions.
SCRYPT_N, SCRYPT_R, SCRYPT_P = 2 ** 14, 8, 1

SCHEMA = [
    "CREATE TABLE IF NOT EXISTS users("
    "id integer GENERATED ALWAYS AS IDENTITY PRIMARY KEY,"
    "username text UNIQUE NOT NULL,"
    "role text NOT NULL CHECK (role IN ('analyst', 'reviewer', 'signer')),"
    "password_hash text NOT NULL,"
    "created_at timestamptz NOT NULL,"
    "disabled boolean NOT NULL DEFAULT false);",

    # The token itself is never stored, only its hash. Deleting a user deletes
    # their sessions with them.
    "CREATE TABLE IF NOT EXISTS sessions("
    "token_hash text PRIMARY KEY,"
    "user_id int NOT NULL REFERENCES users(id) ON DELETE CASCADE,"
    "created_at timestamptz NOT NULL,"
    "expires_at timestamptz NOT NULL);",
]


@dataclass(frozen=True)
class User:
    id: int
    username: str
    role: str

    def public(self) -> dict:
        """What the page is told about the person signed in."""
        return {
            "username": self.username,
            "role": self.role,
            "can_upload": self.role in CAN_UPLOAD,
            "can_decide": self.role in CAN_DECIDE,
        }


# --- passwords ----------------------------------------------------------------

def hash_password(password: str) -> str:
    """A storable scrypt hash, with its salt and cost settings inside it."""
    salt = secrets.token_bytes(16)
    digest = hashlib.scrypt(password.encode(), salt=salt, n=SCRYPT_N, r=SCRYPT_R, p=SCRYPT_P)
    return f"scrypt${SCRYPT_N}${SCRYPT_R}${SCRYPT_P}${salt.hex()}${digest.hex()}"


def verify_password(password: str, stored: str) -> bool:
    """True when password matches the stored hash. Compared in constant time."""
    try:
        scheme, n, r, p, salt, digest = stored.split("$")
        if scheme != "scrypt":
            return False
        attempt = hashlib.scrypt(password.encode(), salt=bytes.fromhex(salt),
                                 n=int(n), r=int(r), p=int(p))
    except (ValueError, TypeError):
        return False
    return hmac.compare_digest(attempt.hex(), digest)


# Checked against when the name does not exist, so a wrong name takes as long
# as a wrong password and the timing does not reveal which names are real.
_DUMMY_HASH = hash_password(secrets.token_hex(16))


def normalise(username: str) -> str:
    """Names are case insensitive: Nara and nara are the same person."""
    return (username or "").strip().lower()


# --- accounts -----------------------------------------------------------------

def create_user(conn, username: str, role: str, password: str) -> User:
    """Add an account. Raises ValueError with a sentence for a person."""
    name = normalise(username)
    if not USERNAME.match(name):
        raise ValueError("A username is 3 to 32 characters: letters, digits, dot, dash or underscore.")
    if role not in ROLES:
        raise ValueError(f"The role must be one of {', '.join(ROLES)}.")
    if len(password) < MIN_PASSWORD:
        raise ValueError(f"A password needs at least {MIN_PASSWORD} characters.")

    taken = ValueError(f"There is already an account called {name}.")
    with conn.cursor() as cur:
        cur.execute("SELECT 1 FROM users WHERE username = %s", (name,))
        if cur.fetchone():
            raise taken
        try:
            cur.execute(
                "INSERT INTO users(username, role, password_hash, created_at) "
                "VALUES (%s, %s, %s, %s) RETURNING id",
                (name, role, hash_password(password), datetime.now(timezone.utc)))
        except psycopg.errors.UniqueViolation:
            # Someone created the same name between the check and the insert.
            conn.rollback()
            raise taken from None
        user_id = cur.fetchone()[0]
    conn.commit()
    return User(user_id, name, role)


def authenticate(conn, username: str, password: str) -> User | None:
    """The account, if the name and password match an active one."""
    with conn.cursor() as cur:
        cur.execute(
            "SELECT id, username, role, password_hash FROM users "
            "WHERE username = %s AND NOT disabled", (normalise(username),))
        row = cur.fetchone()
    if row is None:
        verify_password(password, _DUMMY_HASH)
        return None
    user_id, name, role, stored = row
    return User(user_id, name, role) if verify_password(password, stored) else None


def has_users(conn) -> bool:
    with conn.cursor() as cur:
        cur.execute("SELECT EXISTS (SELECT 1 FROM users)")
        return cur.fetchone()[0]


# --- sessions -----------------------------------------------------------------

def _token_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def start_session(conn, user: User) -> str:
    """Create a session and return its token. Only the hash is stored."""
    token = secrets.token_urlsafe(32)
    now = datetime.now(timezone.utc)
    with conn.cursor() as cur:
        # Expired sessions are swept here, so the table never grows unbounded.
        cur.execute("DELETE FROM sessions WHERE expires_at < %s", (now,))
        cur.execute(
            "INSERT INTO sessions(token_hash, user_id, created_at, expires_at) VALUES (%s, %s, %s, %s)",
            (_token_hash(token), user.id, now, now + timedelta(hours=SESSION_HOURS)))
    conn.commit()
    return token


def user_for_token(conn, token: str | None) -> User | None:
    """The person a session token belongs to, if it is current."""
    if not token:
        return None
    with conn.cursor() as cur:
        cur.execute(
            "SELECT u.id, u.username, u.role FROM sessions s JOIN users u ON u.id = s.user_id "
            "WHERE s.token_hash = %s AND s.expires_at > %s AND NOT u.disabled",
            (_token_hash(token), datetime.now(timezone.utc)))
        row = cur.fetchone()
    return User(*row) if row else None


def end_session(conn, token: str | None) -> None:
    """Sign out: the token stops working at once, everywhere."""
    if not token:
        return
    with conn.cursor() as cur:
        cur.execute("DELETE FROM sessions WHERE token_hash = %s", (_token_hash(token),))
    conn.commit()
