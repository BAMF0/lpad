"""Work-in-progress bug report drafts, stored on disk."""

import contextlib
import hashlib
import time
from dataclasses import dataclass
from pathlib import Path

DRAFT_ROOT = Path.home() / ".local" / "share" / "lpad" / "drafts"

_TITLE_LINE_PREFIX = "Title: "


@dataclass
class Draft:
    id: str
    package: str
    title: str
    description: str
    created_at: float
    path: Path


def _draft_dir(package: str) -> Path:
    return DRAFT_ROOT / package


def _generate_id(package: str, title: str, created_at: float) -> str:
    """Return a short 4-char hash unique within reasonable bounds."""
    raw = f"{created_at}:{package}:{title}"
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:4]


def create_draft(package: str, title: str, description: str) -> Draft:
    """Persist a new draft and return it."""
    created_at = time.time()
    draft_id = _generate_id(package, title, created_at)
    path = _draft_dir(package) / f"{draft_id}.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    content = f"{_TITLE_LINE_PREFIX}{title}\n\n{description}"
    path.write_text(content, encoding="utf-8")
    return Draft(
        id=draft_id,
        package=package,
        title=title,
        description=description,
        created_at=created_at,
        path=path,
    )


def _parse_draft(path: Path, package: str) -> Draft | None:
    try:
        content = path.read_text(encoding="utf-8")
    except OSError:
        return None
    lines = content.splitlines()
    title = ""
    description = ""
    if lines and lines[0].startswith(_TITLE_LINE_PREFIX):
        title = lines[0][len(_TITLE_LINE_PREFIX) :]
        description = "\n".join(lines[2:]) if len(lines) > 2 else ""
    else:
        description = content
    try:
        created_at = path.stat().st_mtime
    except OSError:
        created_at = 0.0
    return Draft(
        id=path.stem,
        package=package,
        title=title,
        description=description,
        created_at=created_at,
        path=path,
    )


def list_drafts(package: str | None = None) -> list[Draft]:
    """List drafts for *package*, or all packages if None."""
    drafts: list[Draft] = []
    roots: list[Path]
    if package is not None:
        roots = [_draft_dir(package)]
    else:
        roots = []
        if DRAFT_ROOT.exists():
            roots = sorted(p for p in DRAFT_ROOT.iterdir() if p.is_dir())
    for root in roots:
        pkg = root.name
        for path in sorted(root.glob("*.md")):
            draft = _parse_draft(path, pkg)
            if draft is not None:
                drafts.append(draft)
    return drafts


def get_draft(draft_id: str, package: str | None = None) -> Draft | None:
    """Return the draft with *draft_id*, optionally scoped to *package*."""
    if package is not None:
        path = _draft_dir(package) / f"{draft_id}.md"
        if path.exists():
            return _parse_draft(path, package)
        return None
    for draft in list_drafts():
        if draft.id == draft_id:
            return draft
    return None


def update_draft(draft: Draft) -> None:
    """Write back the (possibly edited) title and description."""
    content = f"{_TITLE_LINE_PREFIX}{draft.title}\n\n{draft.description}"
    draft.path.write_text(content, encoding="utf-8")


def remove_draft(draft_id: str, package: str | None = None) -> bool:
    """Delete a draft by ID. Returns True if removed, False if not found."""
    draft = get_draft(draft_id, package)
    if draft is None:
        return False
    try:
        draft.path.unlink()
        return True
    except OSError:
        return False


def prune_drafts(
    older_than_days: int = 30,
    dry_run: bool = False,
) -> list[Path]:
    """Return the list of drafts older than *older_than_days*.

    If dry_run is False, also deletes them.
    """
    cutoff = time.time() - older_than_days * 86400
    to_remove: list[Path] = []
    for draft in list_drafts():
        if draft.created_at < cutoff:
            to_remove.append(draft.path)
    if not dry_run:
        for path in to_remove:
            with contextlib.suppress(OSError):
                path.unlink()
    return to_remove
