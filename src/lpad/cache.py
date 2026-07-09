"""File-based cache for Launchpad bug lists and comments.

Bug lists are cached per source package in ~/.cache/lpad/<package>.json.
Comments are cached per bug in ~/.cache/lpad/comments/<bug_id>.json.
Default TTL is 24 hours, overridable via the LPAD_CACHE_TTL environment
variable (value in seconds).
"""

import json
import os
import time
from pathlib import Path

from lpad.bugs import BugSummary, BugWatch, Comment

DEFAULT_TTL = 60 * 60 * 24  # 24 hours
CACHE_DIR = Path.home() / ".cache" / "lpad"
COMMENT_CACHE_DIR = CACHE_DIR / "comments"


def _cache_path(package: str) -> Path:
    return CACHE_DIR / f"{package}.json"


def _comment_cache_path(bug_id: int) -> Path:
    return COMMENT_CACHE_DIR / f"{bug_id}.json"


def _get_ttl() -> int:
    try:
        return int(os.environ.get("LPAD_CACHE_TTL", DEFAULT_TTL))
    except ValueError:
        return DEFAULT_TTL


def _age_string(cached_at: float) -> str:
    age_seconds = int(time.time() - cached_at)
    if age_seconds < 60:
        return f"{age_seconds}s ago"
    elif age_seconds < 3600:
        return f"{age_seconds // 60}m ago"
    else:
        return f"{age_seconds // 3600}h ago"


def _normalize_status_filter(status_filter: list[str] | None) -> list[str] | None:
    """Normalise a status filter for comparison/storage (sorted, or None for all)."""
    if not status_filter:
        return None
    return sorted(status_filter)


# --- Bug list cache ---


def load_cache(
    package: str,
    status_filter: list[str] | None = None,
    ignore_status_filter: bool = False,
) -> list[BugSummary] | None:
    """Load cached bugs for a package.

    Returns a list of BugSummary if the cache exists, is fresh, and was
    fetched with the same status filter. Returns None otherwise (cache
    miss), prompting the caller to refetch.

    When *ignore_status_filter* is True the status-filter comparison is
    skipped — useful for lookups by bug ID (e.g. the fzf preview) where
    the filter that populated the cache is irrelevant.
    """
    path = _cache_path(package)
    if not path.exists():
        return None

    try:
        data = json.loads(path.read_text())
    except (json.JSONDecodeError, OSError):
        return None

    cached_at = data.get("cached_at", 0)
    if time.time() - cached_at > _get_ttl():
        return None

    if not ignore_status_filter:
        cached_filter = data.get("status_filter")
        if cached_filter != _normalize_status_filter(status_filter):
            return None

    return [
        BugSummary(
            id=b.get("id", 0),
            title=b.get("title", "(unknown)"),
            status=b.get("status", "(unknown)"),
            importance=b.get("importance", "Undecided"),
            assignee=b.get("assignee"),
            tags=b.get("tags", []),
            watches=[
                BugWatch(
                    url=w.get("url", ""),
                    title=w.get("title", ""),
                    remote_bug=w.get("remote_bug", ""),
                    remote_status=w.get("remote_status", ""),
                    remote_importance=w.get("remote_importance", ""),
                    date_last_changed=w.get("date_last_changed"),
                )
                for w in b.get("watches", [])
            ],
        )
        for b in data.get("bugs", [])
    ]


def save_cache(
    package: str,
    bugs: list[BugSummary],
    status_filter: list[str] | None = None,
) -> None:
    """Save a list of BugSummary to the cache for the given package."""
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    path = _cache_path(package)
    data = {
        "cached_at": time.time(),
        "status_filter": _normalize_status_filter(status_filter),
        "bugs": [
            {
                "id": b.id,
                "title": b.title,
                "status": b.status,
                "importance": b.importance,
                "assignee": b.assignee,
                "tags": b.tags,
                "watches": [
                    {
                        "url": w.url,
                        "title": w.title,
                        "remote_bug": w.remote_bug,
                        "remote_status": w.remote_status,
                        "remote_importance": w.remote_importance,
                        "date_last_changed": w.date_last_changed,
                    }
                    for w in b.watches
                ],
            }
            for b in bugs
        ],
    }
    path.write_text(json.dumps(data, indent=2))


def invalidate_cache(package: str) -> None:
    """Delete the bug list cache file for the given package."""
    path = _cache_path(package)
    if path.exists():
        path.unlink()


def cache_info(package: str) -> str | None:
    """Return a human-readable string describing the cache age, or None if no cache."""
    path = _cache_path(package)
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text())
    except (json.JSONDecodeError, OSError):
        return None
    age = _age_string(data.get("cached_at", 0))
    return f"cached {age} ({len(data.get('bugs', []))} bugs)"


# --- Comment cache ---


def load_comment_cache(bug_id: int) -> list[Comment] | None:
    """Load cached comments for a bug.

    Returns a list of Comment if the cache exists and is fresh,
    or None if the cache is missing or stale.
    """
    path = _comment_cache_path(bug_id)
    if not path.exists():
        return None

    try:
        data = json.loads(path.read_text())
    except (json.JSONDecodeError, OSError):
        return None

    cached_at = data.get("cached_at", 0)
    if time.time() - cached_at > _get_ttl():
        return None

    return [Comment(**c) for c in data.get("comments", [])]


def save_comment_cache(bug_id: int, comments: list[Comment]) -> None:
    """Save a list of Comments to the cache for the given bug."""
    COMMENT_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    path = _comment_cache_path(bug_id)
    data = {
        "cached_at": time.time(),
        "bug_id": bug_id,
        "comments": [
            {
                "index": c.index,
                "author": c.author,
                "date": c.date,
                "body": c.body,
            }
            for c in comments
        ],
    }
    path.write_text(json.dumps(data, indent=2))


def invalidate_comment_cache(bug_id: int) -> None:
    """Delete the comment cache file for the given bug."""
    path = _comment_cache_path(bug_id)
    if path.exists():
        path.unlink()


def comment_cache_info(bug_id: int) -> str | None:
    """Return a human-readable string describing the comment cache age."""
    path = _comment_cache_path(bug_id)
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text())
    except (json.JSONDecodeError, OSError):
        return None
    age = _age_string(data.get("cached_at", 0))
    return f"cached {age} ({len(data.get('comments', []))} comments)"
