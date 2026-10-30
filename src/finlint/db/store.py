"""Remember every check, so the tool can say what changed and who signed off.

This is step 10 of the architecture in CLAUDE.md Section 7, and it serves the
signer from Section 3: the person who never opens the tool but needs proof the
check happened.

It also feeds lineage/diff.py, which needs a previous run's findings to
compare against, so load_history returns the RunRecords that first_seen
wants and plain Findings inside them.

Every timestamp is stored in UTC. A naive datetime leaves Postgres guessing
from the server's own timezone, which changes when we deploy; local time
repeats an hour when clocks go back, so two events can record the same
instant; and an audit trail has to have exactly one answer to "when". Screens
convert to local time for display.
"""

import hashlib
from datetime import datetime, timezone
from pathlib import Path

from finlint.lineage.diff import RunRecord
from finlint.rules.model import Finding

# Read the workbook in blocks rather than whole, so hashing a large model does
# not pull it all into memory.
HASH_BLOCK = 65536

SCHEMA = [
    # A file is identified by its NAME, because that is what a person tracks:
    # "the Q4 forecast". The content hash lives on the run instead, so an
    # edited file stays the same file and keeps its history.
    "CREATE TABLE IF NOT EXISTS files("
    "id integer GENERATED ALWAYS AS IDENTITY PRIMARY KEY,"
    "name text UNIQUE,"
    "first_seen_at timestamptz);",

    # One row per check. sha256 is the hash of the bytes that were checked, so
    # the same file uploaded twice unchanged can be reported as unchanged
    # rather than pretended to be a new version.
    "CREATE TABLE IF NOT EXISTS runs("
    "id integer GENERATED ALWAYS AS IDENTITY PRIMARY KEY,"
    "file_id int REFERENCES files(id),"
    "version int,"
    "created_at timestamptz,"
    "score int,"
    "report text,"
    "sha256 text);",

    "CREATE TABLE IF NOT EXISTS findings("
    "id integer GENERATED ALWAYS AS IDENTITY PRIMARY KEY,"
    "run_id int REFERENCES runs(id),"
    "rule_id text,"
    "severity text,"
    "sheet text,"
    "coordinate text,"
    "message text,"
    "blast_radius int);",

    # Approvals hang off the FILE, not the run. When somebody marks a hardcode
    # as deliberate, that decision has to survive into every future version,
    # or they would have to mark it again on every upload and the feature
    # would be pointless. The key is the same triple lineage/diff.py uses.
    "CREATE TABLE IF NOT EXISTS approvals("
    "id integer GENERATED ALWAYS AS IDENTITY PRIMARY KEY,"
    "file_id int REFERENCES files(id),"
    "rule_id text,"
    "sheet text,"
    "coordinate text,"
    "reason text,"
    "decided_by text,"
    "decided_at timestamptz);",
]


def file_hash(path) -> str:
    """The SHA-256 of a file's bytes, as hex.

    Two uploads with the same hash are byte for byte the same workbook, which
    is how the history screen can say "nothing changed since v2" instead of
    recording a version that is identical to the one before it.
    """
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        # iter with a sentinel keeps reading blocks until read() returns b"".
        for block in iter(lambda: handle.read(HASH_BLOCK), b""):
            digest.update(block)
    return digest.hexdigest()


def save_run(conn, result) -> int:
    """Store one PipelineResult as a new version of its file. Returns the run id.

    Writes to three tables: files (only if the name is new), runs, and
    findings. It never touches approvals, which are written by a person
    clicking "mark as intentional", not by a check.

    Everything commits once at the end, so a crash halfway cannot leave a run
    with no findings. A run with no findings would make diff_runs report every
    earlier finding as resolved, which is worse than no run at all.
    """
    # The name a person tracks, not the path it happened to be read from.
    # A full path differs on every machine and is not a file identity.
    name = Path(result.path).name
    now = datetime.now(timezone.utc)

    # Hashed BEFORE the transaction opens. Reading a file can fail, and a
    # failure inside the transaction used to leave the earlier inserts pending
    # for whatever the caller committed next: a run row with no findings,
    # which makes diff_runs report every earlier finding as resolved.
    digest = file_hash(result.path)

    # conn.transaction() rolls back on any exception, so a half written run
    # can never reach the database.
    #
    # It is NOT enough on its own. If the caller already has a transaction open,
    # which any plain SELECT leaves behind in psycopg 3, transaction() does not
    # start a new one: it only makes a savepoint inside the open one. The run
    # then looks saved, and is thrown away when the connection closes. The
    # commit after this block is what makes the save durable either way.
    with conn.transaction(), conn.cursor() as cur:
        # 1. Find the file, or create it on first sight.
        cur.execute("SELECT id FROM files WHERE name = %s", (name,))
        row = cur.fetchone()
        if row is None:
            cur.execute(
                "INSERT INTO files(name, first_seen_at) VALUES (%s, %s) RETURNING id",
                (name, now),
            )
            row = cur.fetchone()
        file_id = row[0]

        # 2. Work out the next version number.
        # max() over no rows returns one row holding None, not an empty
        # result, so the test has to be on the VALUE. Checking rowcount here
        # passes and then None + 1 raises TypeError on a file's first run.
        #
        # Two uploads at the same instant could both read the same max and
        # claim the same version. Fine for one user; a real deployment would
        # need a unique constraint on (file_id, version).
        cur.execute("SELECT max(version) FROM runs WHERE file_id = %s", (file_id,))
        highest = cur.fetchone()[0]
        version = 1 if highest is None else highest + 1

        # 3. Insert the run and keep its id, which every finding row needs.
        cur.execute(
            "INSERT INTO runs(file_id, version, created_at, score, report, sha256) "
            "VALUES (%s, %s, %s, %s, %s, %s) RETURNING id",
            (file_id, version, now, result.score, result.report, digest),
        )
        run_id = cur.fetchone()[0]

        # 4. Insert every finding in one statement rather than one at a time.
        cur.executemany(
            "INSERT INTO findings(run_id, rule_id, severity, sheet, coordinate, "
            "message, blast_radius) VALUES (%s, %s, %s, %s, %s, %s, %s)",
            [(run_id, f.rule_id, f.severity, f.sheet, f.coordinate, f.message,
              f.blast_radius) for f in result.findings],
        )

    # Durable even when the caller had a read open: commits the outer
    # transaction that the block above may only have added a savepoint to.
    # With nothing open it does nothing. Only reached on success, so a failed
    # save still leaves nothing behind.
    conn.commit()
    return run_id

def load_history(conn, name) -> list[RunRecord]:
    """Every run of one file, oldest first, with its stored version number.

    Returns RunRecords because first_seen reports the version from the record
    rather than from the list position. Position only agrees with the version
    while the numbers run 1, 2, 3 with nothing missing, and save_run uses
    max(version)+1, so deleting any run but the newest leaves a permanent gap.

    For diff_runs, which wants two plain lists, pass the .findings of two
    records: diff_runs(history[-2].findings, history[-1].findings).

    Ordered by version AND run id. Version alone is not enough: two uploads
    at the same moment can claim the same version number, and SQL gives no
    ordering within equal values, so one run's rows could interleave with
    another's and the grouping below would make extra records.

    Ordered by finding id last, because findings are inserted worst first and
    SQL gives no order within a run otherwise. Without it the page that says
    "worst first" showed a low finding above the critical ones.

    A LEFT JOIN rather than a JOIN, because a plain JOIN drops any run that
    found nothing, and a missing run is a missing version in the history.
    """
    with conn.cursor() as cur:
        cur.execute(
            "SELECT r.id,r.version,f.rule_id,f.severity,f.sheet,f.coordinate,f.message,f.blast_radius "
            "FROM runs r "
            "LEFT JOIN findings f ON f.run_id=r.id "
            "WHERE r.file_id=(SELECT id FROM files WHERE name=%s) "
            "ORDER BY r.version, r.id, f.id ",(name,)
        )

        history=[]
        last_id=None

        rows = cur.fetchall()
        # Ordered by version then run id, so all the rows for one run arrive
        # together and a changing run id is all that is needed to know a new
        # run started. No dictionary required.
        for row in rows:
            # Makes the run's record. Runs for EVERY run, with findings or not.
            if row[0]!=last_id:
                history.append(RunRecord(version=row[1]))
                last_id=row[0]
            # Puts a finding in that record. Runs only when there is one: an
            # empty run comes back as a single row with NULL findings, and it
            # must still get its record. These two tests are deliberately
            # separate rather than if/else, because an elif here appends a
            # second empty record and invents a version that does not exist.
            if row[2] is not None:
                history[-1].findings.append(Finding(
                    rule_id=row[2],
                    severity=row[3],
                    sheet=row[4],
                    coordinate=row[5],
                    message=row[6],
                    blast_radius=row[7]
                ))
        return history


def approve(conn,name,finding,reason,who):
    """Record that a person decided a finding is deliberate, with their reason.

    This is the "mark as intentional" decision from CLAUDE.md Section 10, and
    it is the whole answer to "why can't the AI just fix it". A hardcode can
    be a defect OR a control, and only a human can say which.

    Raises if the file was never checked. You cannot accept a finding on a
    workbook that has no history.

    Raises if this exact finding was never raised by any run of that file.
    Without that check, a caller could approve every cell of a sheet and
    silence findings before they are ever reported, while the approvals table
    showed what looked like a trail of genuine human decisions. For a tool
    whose whole purpose is an audit record, that is a suppression path with no
    way to detect it. It matters more once api/ exposes this to a client.

    Raises on a blank reason or decider. An approval with no reason still
    greys the finding out, so it would hide a defect while recording nothing
    about who hid it or why. The reason IS the control here.

    Approving the same cell twice deliberately inserts a SECOND row rather
    than updating the first. This is an audit trail: who decided what, when
    and why is the point, and a later decision with a different reason is real
    history. Do not add a unique constraint here thinking it is a bug fix.
    """
    if not reason or not reason.strip():
        raise ValueError("An approval needs a reason")
    if not who or not who.strip():
        raise ValueError("An approval needs to say who decided it")

    with conn.cursor() as cur:
        cur.execute("SELECT id FROM files WHERE name=%s",(name,))
        row=cur.fetchone()
        if row is None:
            raise ValueError(f"File {name} not found in history")
        file_id=row[0]

        # The finding has to have actually been raised on this file. Checked
        # against findings joined to that file's runs, using the same triple
        # finding_key and load_approvals use, so all three agree on identity.
        cur.execute(
            "SELECT 1 FROM findings f JOIN runs r ON r.id = f.run_id "
            "WHERE r.file_id = %s AND f.rule_id = %s AND f.sheet = %s "
            "AND f.coordinate = %s LIMIT 1",
            (file_id, finding.rule_id, finding.sheet, finding.coordinate),
        )
        if cur.fetchone() is None:
            raise ValueError(
                f"{finding.rule_id} at {finding.sheet}!{finding.coordinate} "
                f"was never reported for {name}, so it cannot be approved"
            )

        cur.execute("INSERT INTO approvals(file_id,rule_id,sheet,coordinate,reason,decided_by,decided_at) VALUES (%s,%s,%s,%s,%s,%s,%s)",
                    (file_id,finding.rule_id,finding.sheet,finding.coordinate,reason,who,datetime.now(timezone.utc)))

        conn.commit()


def load_approvals(conn,name) -> set[tuple[str, str, str]]:
    """Every finding a person has already accepted on this file.

    Returns a set of (rule_id, sheet, coordinate) in exactly the order
    finding_key uses, so a caller can test `finding_key(f) in approvals`
    with no conversion. That is the only reason for this shape.

    The set collapses repeated approvals of one cell, which is what "has this
    been accepted" needs, while the table keeps every individual decision.

    An unknown file returns an empty set rather than raising, because showing
    a never-checked file with nothing accepted is a sensible answer.
    """
    with conn.cursor() as cur:
        cur.execute("SELECT a.rule_id,a.sheet,a.coordinate FROM approvals a WHERE a.file_id=(SELECT id FROM files WHERE name=%s)",(name,))
        rows=cur.fetchall()

        return {(row[0],row[1],row[2]) for row in rows}
        
        
    
        
    