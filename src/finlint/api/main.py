"""The FinLint API: the doorway between the engine and the web page.

Every route follows docs/api_contract.md exactly. The route bodies are thin on
purpose: the JSON itself is built in api/views.py, the same module the saved
sample is exported with, so the live API and the sample cannot disagree.

Run it from the repository root:

    uvicorn finlint.api.main:app --port 8000

Then http://localhost:8000 is the whole product, and http://localhost:8000/docs
lists every endpoint with a form to try it.

Everything except /api/health and signing in needs an account. Roles and what
each may do are defined in finlint/auth.py; the limits on how often anyone can
call are defined below and enforced by finlint/ratelimit.py.

Every route is a plain def, not async def. Reading a workbook and talking to
PostgreSQL both block, and FastAPI runs a plain def on a worker thread, while a
blocking async def would freeze the server for every other user.
"""

import collections
import hashlib
import json
import logging
import math
import os
import threading
import time
from contextlib import asynccontextmanager
from pathlib import Path
from urllib.parse import urlsplit

import psycopg
from fastapi import Depends, FastAPI, File, HTTPException, Request, Response, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from finlint import auth, storage
from finlint.api import views
from finlint.db.store import SCHEMA, approve, save_run
from finlint.graph.build import build_graph
from finlint.parsing.reader import read_workbook
from finlint.pipeline import check_file
from finlint.rag.store import CONNECT_TIMEOUT, DATABASE_URL, connect
from finlint.rag.store import SCHEMA as RAG_SCHEMA
from finlint.ratelimit import RateLimiter
from finlint.rules.model import Finding

VERSION = "0.1.0"

# The built website (npm run build in web/). Served by this same app, so the
# whole product is one process and one URL.
FRONTEND = Path(os.getenv("FINLINT_WEB", "web/out"))

# The measured results the Evaluation page shows.
EVALUATION = Path(os.getenv("FINLINT_EVALUATION", "docs/evaluation.json"))

# The model the Standards agent asks. Overridable without a code change.
MODEL = os.getenv("FINLINT_MODEL", "qwen/qwen3.8-27b")

# Other origins allowed to call the API with the session cookie: only the
# development page on port 3000. The container sets this empty, because there
# the page and the API share one origin and nothing else should be let in.
# Not 127.0.0.1:3000: the browser treats it as another site from localhost and
# drops the cookie, so signing in silently failed there (found in review).
DEV_ORIGINS = [o for o in os.getenv("FINLINT_CORS_ORIGINS", "http://localhost:3000").split(",") if o]

# Largest request body accepted. An upload may be a workbook plus the form
# wrapper around it; anything else is a small JSON body.
UPLOAD_BODY_LIMIT = storage.MAX_BYTES + 1024 * 1024
BODY_LIMIT = 64 * 1024

# The longest /api/health waits for the database before calling it off.
HEALTH_PROBE_SECONDS = 1.0

# How many parsed workbooks to keep in memory. Reading one takes about a second
# for a large model, and the inspector asks about one cell at a time.
WORKBOOK_CACHE = 8

# The cookie that carries a signed in session. HttpOnly, so the page's own
# scripts cannot read it and an injected script cannot steal it.
SESSION_COOKIE = "finlint_session"

# Rate limits, as (requests, seconds). See finlint/ratelimit.py for why.
API_LIMIT = (240, 60)            # any /api call, per address
LOGIN_FAILURES = (5, 15 * 60)    # wrong passwords for one name, per address
LOGIN_FAILURES_PER_ADDRESS = (20, 15 * 60)
UPLOAD_LIMIT = (10, 60)          # workbooks checked, per person
EXPLAIN_LIMIT = (6, 60)          # standards questions, per person
EXPLAIN_LIMIT_SERVER = (10, 60)  # for everyone together: Groq allows 30 calls
                                 # a minute and one question uses up to three

limiter = RateLimiter()

log = logging.getLogger("finlint.api")


class StoredFileMissing(LookupError):
    """A version exists in the history, but its workbook was never stored."""


# --- startup ---------------------------------------------------------------

@asynccontextmanager
async def lifespan(_app: FastAPI):
    """Prepare the database and the embedding model before the first person."""
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    try:
        ensure_schema()
        log.info("database ready")
    except psycopg.Error:
        # The API still starts: /api/health reports the database as off and the
        # page explains it, which is better than refusing to run at all. The
        # first request after the database comes back creates the tables.
        log.warning("database not ready at startup; /api/health will report it")

    # Load the embedding model now, in the background. Loaded on first use
    # instead, the first "Find a supporting standard" took 77 seconds, measured,
    # nearly all of it importing torch and reading the model.
    threading.Thread(target=warm_up, name="warm-up", daemon=True).start()
    yield


def warm_up():
    """Load the embedding model once, so no person waits for it."""
    try:
        from finlint.rag.store import embed
        started = time.perf_counter()
        embed(["warm up"])
        log.info("embedding model ready in %.0fs", time.perf_counter() - started)
    except Exception:
        # Not fatal: the first search loads it instead, only slower.
        log.exception("could not preload the embedding model")


app = FastAPI(title="FinLint", version=VERSION, lifespan=lifespan)


def client_address(request: Request) -> str:
    return request.client.host if request.client else "unknown"


def refuse(status: int, detail: str, headers: dict | None = None) -> JSONResponse:
    return JSONResponse(status_code=status, content={"detail": detail}, headers=headers)


def same_site_origin(request: Request) -> bool:
    """True when a POST comes from this site or an allowed development page.

    Browsers always send Origin on a cross site POST. Refusing a foreign one
    stops another site (or another program on another localhost port) from
    using a signed in person's cookie to act for them. Tools that send no
    Origin, such as curl, are not a browser carrying someone's cookie.
    """
    origin = request.headers.get("origin")
    if not origin:
        return True
    return origin in DEV_ORIGINS or urlsplit(origin).netloc == request.headers.get("host")


@app.middleware("http")
async def guard_requests(request: Request, call_next):
    """Cheap refusals that must happen before a request body is read.

    FastAPI reads and parses the whole body before any route dependency runs,
    so without this an anonymous caller could make the server receive a
    400 MB upload before being told to sign in (found in review: 38 seconds).

    Also a generous ceiling on API calls from one address: one click on the
    page makes a handful of calls, so this stops a script, not a person.
    """
    path = request.url.path
    if not path.startswith("/api") or request.method == "OPTIONS":
        return await call_next(request)

    wait = limiter.hit(f"api:{client_address(request)}", *API_LIMIT)
    if wait:
        seconds = math.ceil(wait)
        return refuse(429, f"Too many requests from this address. Try again in {seconds} seconds.",
                      {"Retry-After": str(seconds)})

    if request.method == "POST":
        if not same_site_origin(request):
            return refuse(403, "This request came from another website and was refused.")
        size = request.headers.get("content-length")
        if path == "/api/check":
            if SESSION_COOKIE not in request.cookies:
                return refuse(401, "Sign in to use FinLint.")
            if size is None:
                return refuse(411, "The upload must say its size.")
        upload = path == "/api/check"
        limit = UPLOAD_BODY_LIMIT if upload else BODY_LIMIT
        if size is not None and (not size.isdigit() or int(size) > limit):
            return refuse(413, f"The workbook is larger than {storage.MAX_BYTES // (1024 * 1024)} MB."
                          if upload else "The request is too large.")
    return await call_next(request)


@app.middleware("http")
async def log_requests(request: Request, call_next):
    """One line per API request: method, path, status and time taken.

    This is the "see what happened when something breaks" half of the Week 6
    logging task. Static files are skipped, or every page load would bury the
    API lines under dozens of script and font requests.
    """
    started = time.perf_counter()
    status = 500  # stays 500 if call_next raises, so failures are logged too
    try:
        response = await call_next(request)
        status = response.status_code
        return response
    finally:
        if request.url.path.startswith("/api"):
            elapsed = (time.perf_counter() - started) * 1000
            log.info("%s %s %s %.0fms", request.method, request.url.path, status, elapsed)


# Added last, so it wraps everything above. Credentials are allowed so the
# development page on port 3000 can send its session cookie to port 8000.
app.add_middleware(
    CORSMiddleware,
    allow_origins=DEV_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type"],
)


_schema_ready = False
_schema_lock = threading.Lock()


def ensure_schema():
    """Create the extension and every table once per process, if missing.

    Uses a plain connection: connect() registers the vector type, which fails
    on a fresh database where the extension does not exist yet.
    """
    global _schema_ready
    with _schema_lock:
        if _schema_ready:
            return
        if not DATABASE_URL:
            raise psycopg.OperationalError("DATABASE_URL is not set")
        with psycopg.connect(DATABASE_URL, connect_timeout=CONNECT_TIMEOUT) as conn:
            for statement in RAG_SCHEMA + SCHEMA + auth.SCHEMA:
                conn.execute(statement)
        _schema_ready = True


# --- errors, each turned into a sentence the page can show ------------------

@app.exception_handler(views.NotFound)
def not_found(_request: Request, error: views.NotFound):
    return JSONResponse(status_code=404, content={"detail": str(error)})


@app.exception_handler(StoredFileMissing)
def stored_file_missing(_request: Request, error: StoredFileMissing):
    return JSONResponse(status_code=404, content={"detail": str(error)})


@app.exception_handler(storage.RejectedUpload)
def rejected_upload(_request: Request, error: storage.RejectedUpload):
    return JSONResponse(status_code=400, content={"detail": str(error)})


@app.exception_handler(psycopg.OperationalError)
def database_down(_request: Request, error: psycopg.OperationalError):
    log.warning("database unavailable: %s", error)
    return JSONResponse(
        status_code=503,
        content={"detail": "The database is not reachable. Check that PostgreSQL is running."},
    )


@app.exception_handler(Exception)
def unexpected(request: Request, error: Exception):
    # The full trace goes to the log for us; the page gets a sentence, never
    # internals.
    # exc_info is passed explicitly: this handler runs on a worker thread where
    # there is no "current" exception, so log.exception alone logged nothing.
    log.error("unhandled error on %s %s", request.method, request.url.path, exc_info=error)
    return JSONResponse(status_code=500, content={"detail": "Something went wrong on the server. It has been logged."})


# --- shared pieces ---------------------------------------------------------

def db():
    """One connection per request, always closed when the request ends.

    A single shared connection would be used by several worker threads at once,
    which psycopg does not allow.
    """
    ensure_schema()
    conn = connect()
    try:
        yield conn
    finally:
        conn.close()


_parsed: "collections.OrderedDict[tuple[str, str], tuple]" = collections.OrderedDict()
_parsed_lock = threading.Lock()


def parsed(sha256: str, name: str):
    """The workbook and dependency graph for one stored version, cached.

    Keyed by hash as well as name, so a new version of the same workbook is
    never answered from the old one. The lock guards only the cache itself.
    Parsing happens outside it, so one large workbook being read never holds
    up requests about other files. Two first requests for the same file may
    both parse it; the result is identical, so either copy is fine.
    """
    key = (sha256, name)
    with _parsed_lock:
        if key in _parsed:
            _parsed.move_to_end(key)
            return _parsed[key]

    path = storage.path_for(sha256, name)
    if not path.exists():
        raise StoredFileMissing(
            f"The workbook for this version of {name} was not kept, so it cannot be opened. "
            "Check the workbook again to store it."
        )
    workbook = read_workbook(str(path))
    value = (workbook, build_graph(workbook))

    with _parsed_lock:
        _parsed[key] = value
        _parsed.move_to_end(key)
        while len(_parsed) > WORKBOOK_CACHE:
            _parsed.popitem(last=False)
    return value


def current_user(request: Request, conn=Depends(db)) -> auth.User:
    """The person signed in, or 401. Every data route depends on this."""
    user = auth.user_for_token(conn, request.cookies.get(SESSION_COOKIE))
    if user is None:
        raise HTTPException(status_code=401, detail="Sign in to use FinLint.")
    return user


def allowed(roles: tuple[str, ...], action: str):
    """A dependency that lets only these roles through, with a reason if not."""
    def check(user: auth.User = Depends(current_user)) -> auth.User:
        if user.role not in roles:
            raise HTTPException(
                status_code=403,
                detail=f"Your account is a {user.role}, and a {user.role} cannot {action}.",
            )
        return user
    return check


def too_many(wait: float, message: str) -> HTTPException:
    seconds = math.ceil(wait)
    return HTTPException(status_code=429, detail=f"{message} Try again in {seconds} seconds.",
                         headers={"Retry-After": str(seconds)})


def latest_sha(conn, name: str) -> str:
    """The hash of the newest stored version of a workbook."""
    with conn.cursor() as cur:
        cur.execute(
            "SELECT r.sha256 FROM runs r JOIN files f ON f.id = r.file_id "
            "WHERE f.name = %s ORDER BY r.version DESC, r.id DESC LIMIT 1", (name,))
        row = cur.fetchone()
    if row is None:
        raise views.NotFound(f"{name} has not been checked yet.")
    return row[0]


def run_detail(conn, name: str) -> dict:
    """GET /api/files/{name}/run, shared with the upload route."""
    workbook, graph = parsed(latest_sha(conn, name), name)
    return views.run_body(conn, name, workbook, graph)


# --- routes ----------------------------------------------------------------

@app.get("/api/health")
def health():
    """What is connected, so the page can switch features on or off honestly.

    Never fails, and answers within about a second. The probe runs on its own
    thread because libpq waits at least two seconds per address whatever
    connect_timeout says, and "localhost" tries two addresses: a stopped
    database took four seconds to report, measured, longer than the page waits.
    """
    result = {"database": False}

    def probe():
        try:
            psycopg.connect(DATABASE_URL, connect_timeout=2).close()
            result["database"] = True
        except Exception:
            pass

    worker = threading.Thread(target=probe, daemon=True)
    worker.start()
    worker.join(HEALTH_PROBE_SECONDS)
    return {"ok": True, "database": result["database"],
            "llm": bool(os.getenv("GROQ_API_KEY")), "version": VERSION}


# --- signing in ---------------------------------------------------------------

class LoginRequest(BaseModel):
    # Capped, because every name tried is a key in the rate limiter's memory.
    username: str = Field(max_length=64)
    password: str = Field(max_length=1024)


@app.post("/api/auth/login")
def login(body: LoginRequest, request: Request, response: Response, conn=Depends(db)):
    """Check a name and password, and start a session in a cookie.

    Every attempt is counted BEFORE the password is checked, in one locked
    step, and a correct one is then taken back. Counting only after a failure
    let a burst of simultaneous guesses all pass the check first. The same
    message is given for a wrong name and a wrong password, so the page does
    not reveal which names exist.
    """
    name = auth.normalise(body.username)
    address = client_address(request)
    per_name, per_address = f"login:{address}:{name}", f"login:{address}"
    wait = limiter.hit_all([(per_name, *LOGIN_FAILURES), (per_address, *LOGIN_FAILURES_PER_ADDRESS)])
    if wait:
        raise too_many(wait, "Too many wrong passwords.")

    user = auth.authenticate(conn, name, body.password)
    if user is None:
        log.warning("failed sign in for %r from %s", name, address)
        raise HTTPException(status_code=401, detail="That username and password do not match an account.")

    # A correct password is not a failure: give both counts back.
    limiter.clear(per_name)
    limiter.undo(per_address)
    response.set_cookie(
        SESSION_COOKIE,
        auth.start_session(conn, user),
        max_age=auth.SESSION_HOURS * 3600,
        httponly=True,
        samesite="lax",
        secure=request.url.scheme == "https",
        path="/",
    )
    log.info("%s signed in as %s", user.username, user.role)
    return user.public()


@app.post("/api/auth/logout")
def logout(request: Request, response: Response, conn=Depends(db)):
    auth.end_session(conn, request.cookies.get(SESSION_COOKIE))
    response.delete_cookie(SESSION_COOKIE, path="/")
    return {"ok": True}


@app.get("/api/auth/me")
def me(request: Request, conn=Depends(db)):
    """Who is signed in, and what they may do. 401 if nobody."""
    user = auth.user_for_token(conn, request.cookies.get(SESSION_COOKIE))
    if user is None:
        if not auth.has_users(conn):
            raise HTTPException(
                status_code=401,
                detail="No accounts exist yet. Create one with: python scripts/create_user.py <name> --role reviewer",
            )
        raise HTTPException(status_code=401, detail="Sign in to use FinLint.")
    return user.public()


# --- workbooks ---------------------------------------------------------------

@app.get("/api/files")
def files(conn=Depends(db), _user=Depends(current_user)):
    return views.files_body(conn)


@app.post("/api/check")
def check(file: UploadFile = File(...), conn=Depends(db),
          user: auth.User = Depends(allowed(auth.CAN_UPLOAD, "upload workbooks"))):
    """Store an uploaded workbook, run every check on it, save it as a version.

    Only the deterministic engine runs here: no model, so the same file always
    gets the same findings and the same score. Citations are asked for one
    finding at a time, through /api/explain.
    """
    wait = limiter.hit(f"upload:{user.id}", *UPLOAD_LIMIT)
    if wait:
        raise too_many(wait, f"You have checked {UPLOAD_LIMIT[0]} workbooks in the last minute.")

    # Read one byte past the limit, so an oversized file is caught without
    # pulling all of it into memory.
    data = file.file.read(storage.MAX_BYTES + 1)
    name = storage.safe_name(file.filename)
    existed = storage.path_for(hashlib.sha256(data).hexdigest(), name).exists()
    path = storage.store(data, name)

    try:
        result = check_file(str(path))
    except Exception:
        log.exception("could not read upload %s", name)
        # A file that cannot be read is not kept, unless an earlier upload
        # already stored the same bytes. Its folder goes too, if now empty.
        if not existed:
            path.unlink(missing_ok=True)
            try:
                path.parent.rmdir()
            except OSError:
                pass
        raise storage.RejectedUpload(f"{name} could not be read as an Excel workbook.")

    save_run(conn, result)
    return run_detail(conn, name)


@app.get("/api/files/{name}/run")
def run(name: str, conn=Depends(db), _user=Depends(current_user)):
    return run_detail(conn, name)


@app.get("/api/files/{name}/history")
def history(name: str, conn=Depends(db), _user=Depends(current_user)):
    return views.history_body(conn, name)


@app.get("/api/files/{name}/cell")
def cell(name: str, ref: str, conn=Depends(db), _user=Depends(current_user)):
    """Everything the inspector shows for one cell, given as Sheet!A1."""
    sheet, separator, coordinate = ref.rpartition("!")
    if not separator or not sheet or not coordinate:
        raise HTTPException(status_code=400, detail=f"{ref} is not a cell reference like Sheet!A1.")
    workbook, graph = parsed(latest_sha(conn, name), name)
    return views.inspect_cell(workbook, graph, sheet, coordinate.upper())


class ExplainRequest(BaseModel):
    file: str
    finding: Finding


@app.post("/api/explain")
def explain(body: ExplainRequest, conn=Depends(db), user: auth.User = Depends(current_user)):
    """Ask the Standards agent about one finding.

    One finding per call on purpose: each costs one to three Groq calls, and the
    free tier allows 30 a minute. Every quote it returns has already been found
    word for word in the stored document, and the source, page and link come
    from that stored passage, never from the model.
    """
    if not os.getenv("GROQ_API_KEY"):
        raise HTTPException(
            status_code=503,
            detail="The standards agent is off: set GROQ_API_KEY on the server to enable it.",
        )
    # Both limits are checked and counted together in one locked step, so a
    # question refused by either does not use up the other.
    mine, everyone = f"explain:{user.id}", "explain:server"
    if limiter.wait_needed(mine, *EXPLAIN_LIMIT):
        message = f"You have asked {EXPLAIN_LIMIT[0]} standards questions in the last minute."
    else:
        message = "The standards agent is busy with other people's questions."
    wait = limiter.hit_all([(mine, *EXPLAIN_LIMIT), (everyone, *EXPLAIN_LIMIT_SERVER)])
    if wait:
        raise too_many(wait, message)

    from finlint.agents.groq_provider import groq_completion
    from finlint.agents.standards import explain_with_retriever

    latest_sha(conn, body.file)  # a finding for a workbook nobody checked is refused
    try:
        result = explain_with_retriever(conn, body.finding, groq_completion(MODEL), limit=5)
    except psycopg.Error:
        raise
    except Exception:
        log.exception("standards agent failed for %s", body.finding.rule_id)
        raise HTTPException(
            status_code=502,
            detail="The standards agent did not answer. It may be rate limited; try again in a minute.",
        )
    return result.model_dump()


@app.get("/api/files/{name}/approvals")
def approvals(name: str, conn=Depends(db), _user=Depends(current_user)):
    return views.approvals_body(conn, name)


class ApprovalRequest(BaseModel):
    file: str
    finding: Finding
    reason: str
    # Ignored, kept so older clients still validate. Who decided is always the
    # account signed in: a typed name let anyone record a decision as anyone.
    who: str | None = None


@app.post("/api/approvals")
def record_approval(body: ApprovalRequest, conn=Depends(db),
                    user: auth.User = Depends(allowed(auth.CAN_DECIDE, "mark findings as intentional"))):
    """Record that a person decided a finding is deliberate, and why.

    Only a reviewer may: the analyst who built the model must not sign off its
    own findings (segregation of duties). The decider is the account signed in.

    db.store.approve refuses an unknown file, a finding that was never
    reported, and a blank reason. Each refusal is a sentence the page shows as
    it is.
    """
    try:
        approve(conn, body.file, body.finding, body.reason.strip(), user.username)
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error))

    key = (body.finding.rule_id, body.finding.sheet, body.finding.coordinate)
    stored = [a for a in views.approvals_body(conn, body.file)
              if (a["rule_id"], a["sheet"], a["coordinate"]) == key]
    return stored[0]  # newest first, so this is the decision just recorded


@app.get("/api/evaluation")
def evaluation(_user=Depends(current_user)):
    if not EVALUATION.exists():
        raise views.NotFound("The evaluation results file is missing.")
    return json.loads(EVALUATION.read_text(encoding="utf-8"))


@app.api_route("/api/{path:path}", methods=["GET", "POST", "PUT", "PATCH", "DELETE"])
def unknown_api_path(path: str):
    """An /api address that does not exist gets JSON, not the website's page."""
    raise HTTPException(status_code=404, detail=f"There is no API endpoint at /api/{path}.")


# --- the website, mounted LAST ----------------------------------------------
# Mounted at "/" after every route. Registered first, it would answer every
# request, /api included, and the API would vanish behind the website.
if FRONTEND.is_dir():
    app.mount("/", StaticFiles(directory=FRONTEND, html=True), name="web")
else:
    log.info("no built website at %s; run npm run build in web/ to serve it here", FRONTEND)
