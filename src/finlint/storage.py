"""Keep every uploaded workbook, so any past version can be inspected again.

Each upload is written to

    <uploads>/<sha256 of the bytes>/<original file name>

which gives three properties at once:

- Every version is kept. A changed workbook has different bytes, so a
  different hash and a different folder. Nothing is ever overwritten.
- The same bytes uploaded twice are stored once, in the same folder.
- The original file name survives as the last path component. That matters
  because db.store.save_run identifies a workbook by Path(path).name, so the
  stored path must end in the name a person recognises, not in a hash.

FinLint never writes to a workbook it reads. This module writes a copy of the
upload once and never touches it again.
"""

import hashlib
import os
import tempfile
from pathlib import Path

# Excel formats openpyxl can read. .xlsm keeps its macros out of our way: they
# are stored but never run.
ACCEPTED_SUFFIXES = (".xlsx", ".xlsm")

# A generous ceiling. The largest seed model is about 2 MB; anything near this
# is far more likely to be a mistake or an attack than a forecast.
MAX_BYTES = 50 * 1024 * 1024

# Not allowed in a Windows file name. Refused everywhere, so a name stored on
# one machine can be opened on any other.
FORBIDDEN = set('<>:"|?*')


class RejectedUpload(ValueError):
    """The upload is not something FinLint will store. The message is for a person."""


def uploads_dir() -> Path:
    """Where uploads live. Read on every call, so tests can point it elsewhere."""
    return Path(os.getenv("FINLINT_UPLOADS", "data/uploads"))


def safe_name(filename: str | None) -> str:
    """The original file name, reduced to a single safe path component.

    Browsers send only a name, but a crafted request can send "../../x.xlsx"
    or a Windows path. Everything up to the last slash or backslash is
    dropped, so the result can never point outside its own folder.
    """
    name = (filename or "").replace("\\", "/").rsplit("/", 1)[-1].strip()
    if not name or name.startswith("."):
        raise RejectedUpload("The upload needs a file name ending in .xlsx or .xlsm.")
    # Characters Windows forbids in a file name. The colon matters most:
    # "C:model.xlsx" survives the slash stripping above, yet Windows reads it as
    # a path on drive C, outside the uploads folder. Found in review.
    if any(c in FORBIDDEN for c in name) or any(ord(c) < 32 for c in name):
        raise RejectedUpload(f"{name} contains a character a file name cannot have, such as : ? * or |.")
    if not name.lower().endswith(ACCEPTED_SUFFIXES):
        raise RejectedUpload(f"{name} is not an Excel workbook. FinLint reads .xlsx and .xlsm files.")
    return name


def store(data: bytes, filename: str | None) -> Path:
    """Write one upload to storage and return its path. Safe to call twice."""
    name = safe_name(filename)
    if not data:
        raise RejectedUpload(f"{name} is empty.")
    if len(data) > MAX_BYTES:
        raise RejectedUpload(f"{name} is larger than {MAX_BYTES // (1024 * 1024)} MB.")

    folder = uploads_dir() / hashlib.sha256(data).hexdigest()
    path = folder / name
    if path.parent != folder:  # belt and braces: never outside its own folder
        raise RejectedUpload(f"{name} is not a plain file name.")
    folder.mkdir(parents=True, exist_ok=True)
    if not path.exists():
        # Written to a temporary file first and then renamed, so a crash
        # halfway can never leave a truncated workbook under the real name.
        # The temporary name is unique, so two uploads of the same file at
        # once (a double click) never write to the same partial file.
        handle, partial = tempfile.mkstemp(dir=folder, prefix=".", suffix=".partial")
        try:
            with os.fdopen(handle, "wb") as out:
                out.write(data)
            os.replace(partial, path)
        except OSError:
            # The other upload won the rename. Same bytes, so its copy is ours.
            if not path.exists():
                raise
        finally:
            if os.path.exists(partial):
                os.remove(partial)
    return path


def path_for(sha256: str, name: str) -> Path:
    """Where a stored version lives, from the hash and name in the runs table."""
    return uploads_dir() / sha256 / safe_name(name)
