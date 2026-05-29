"""File-based cache for Launchpad bug lists.

Bugs are cached per source package in ~/.cache/lpad/<package>.json.
Default TTL is 24 hours, overridable via the LPAD_CACHE_TTL environment
variable (value in seconds).
"""

import json
import os
import time
from pathlib import Path

from lpad.bugs import BugSummary

DEFAULT_TTL = 60 * 60 * 24  # 24 hours
CACHE_DIR = Path.home() / ".cache" / "lpad"


def _cache_path(package: str) -> Path:
    return CACHE_DIR / f"{package}.json"


def _get_ttl() -> int:
    try:
        return int(os.environ.get("LPAD_CACHE_TTL", DEFAULT_TTL))
    except ValueError:
        return DEFAULT_TTL


def load_cache(package: str) -> list[BugSummary] | None:
    """Load cached bugs for a package.

    Returns a list of BugSummary if the cache exists and is fresh,
    or None if the cache is missing or stale.
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

    return [BugSummary(**b) for b in data.get("bugs", [])]


def save_cache(package: str, bugs: list[BugSummary]) -> None:
    """Save a list of BugSummary to the cache for the given package."""
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    path = _cache_path(package)
    data = {
        "cached_at": time.time(),
        "bugs": [
            {
                "id": b.id,
                "title": b.title,
                "status": b.status,
                "importance": b.importance,
                "assignee": b.assignee,
                "tags": b.tags,
            }
            for b in bugs
        ],
    }
    path.write_text(json.dumps(data, indent=2))


def invalidate_cache(package: str) -> None:
    """Delete the cache file for the given package."""
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
    cached_at = data.get("cached_at", 0)
    age_seconds = int(time.time() - cached_at)
    if age_seconds < 60:
        age = f"{age_seconds}s ago"
    elif age_seconds < 3600:
        age = f"{age_seconds // 60}m ago"
    else:
        age = f"{age_seconds // 3600}h ago"
    return f"cached {age} ({len(data.get('bugs', []))} bugs)"
