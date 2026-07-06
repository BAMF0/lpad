"""Open the user's $EDITOR on seeded content and return the result."""

import contextlib
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import lpad.color as col

TMP_DIR = Path.home() / ".local" / "share" / "lpad" / "tmp"


def _resolve_editor() -> str | None:
    """Return the first available editor command.

    Order of precedence: $VISUAL, $EDITOR, sensible-editor, nano, vi.
    """
    candidates = [
        os.environ.get("VISUAL"),
        os.environ.get("EDITOR"),
        "sensible-editor",
        "nano",
        "vi",
    ]
    for cmd in candidates:
        if not cmd:
            continue
        basename = cmd.split()[0]
        if shutil.which(basename):
            return cmd
    return None


def open_editor(seed_content: str, suffix: str = ".md") -> str | None:
    """Open $EDITOR on a temp file seeded with *seed_content*.

    Returns the edited content as a string, or None if the user saved an
    empty file (caller decides whether to abort).

    Exits with a clear error if no editor is available.
    """
    editor = _resolve_editor()
    if editor is None:
        print(
            col.error("Error: no editor found. Set $EDITOR or install nano/vi."),
            file=sys.stderr,
        )
        sys.exit(1)

    TMP_DIR.mkdir(parents=True, exist_ok=True)
    fd, tmp_path = tempfile.mkstemp(suffix=suffix, dir=str(TMP_DIR))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(seed_content)
        try:
            subprocess.call([editor, tmp_path])
        except OSError as exc:
            print(
                col.error(f"Error: could not launch editor '{editor}': {exc}"),
                file=sys.stderr,
            )
            sys.exit(1)
        try:
            with open(tmp_path, encoding="utf-8") as fh:
                content = fh.read()
        except OSError as exc:
            print(
                col.error(f"Error: could not read edited file: {exc}"),
                file=sys.stderr,
            )
            sys.exit(1)
    finally:
        with contextlib.suppress(OSError):
            os.unlink(tmp_path)

    if not content.strip():
        return None
    return content
