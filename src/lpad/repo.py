"""Detect the Launchpad source package from the current git repository."""

import re
import subprocess
import sys

# Patterns for Launchpad source package remote URLs
# e.g. git+ssh://git.launchpad.net/~user/ubuntu/+source/curl
#      https://git.launchpad.net/~user/ubuntu/+source/curl
#      git+ssh://git.launchpad.net/ubuntu/+source/curl  (team-less)
_SOURCE_PKG_RE = re.compile(
    r"git\.launchpad\.net/(?:[^/]+/)*\+source/([^/\s]+)"
)


def _get_remote_url(remote: str = "origin") -> str | None:
    """Return the URL for the given git remote, or None if not found."""
    try:
        result = subprocess.run(
            ["git", "remote", "get-url", remote],
            capture_output=True,
            text=True,
            check=True,
        )
        return result.stdout.strip()
    except subprocess.CalledProcessError:
        return None


def detect_source_package() -> str:
    """Detect the Ubuntu source package name from the current git remote.

    Tries 'origin' first, then all remotes. Falls back to prompting the user
    if no Launchpad source package URL is found.

    Returns the source package name (e.g. 'curl').
    """
    # Try origin first
    url = _get_remote_url("origin")
    if url:
        m = _SOURCE_PKG_RE.search(url)
        if m:
            return m.group(1)

    # Try all remotes
    try:
        result = subprocess.run(
            ["git", "remote"],
            capture_output=True,
            text=True,
            check=True,
        )
        remotes = result.stdout.strip().splitlines()
        for remote in remotes:
            url = _get_remote_url(remote)
            if url:
                m = _SOURCE_PKG_RE.search(url)
                if m:
                    return m.group(1)
    except subprocess.CalledProcessError:
        pass

    # Fall back to user prompt
    print(
        "Could not detect source package from git remote.",
        file=sys.stderr,
    )
    pkg = input("Enter source package name: ").strip()
    if not pkg:
        print("Error: source package name cannot be empty.", file=sys.stderr)
        sys.exit(1)
    return pkg


def get_current_branch() -> str | None:
    """Return the current git branch name, or None if not in a git repo."""
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],
            capture_output=True,
            text=True,
            check=True,
        )
        return result.stdout.strip()
    except subprocess.CalledProcessError:
        return None


def parse_bug_number_from_branch(branch: str) -> int | None:
    """Parse a bug number from a branch name like lp1234567-fix-crash.

    Returns the bug number as an int, or None if the branch doesn't match.
    """
    m = re.match(r"^lp(\d+)", branch)
    if m:
        return int(m.group(1))
    return None
