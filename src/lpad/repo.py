"""Detect the Launchpad source package from the current git repository."""

import os
import re
import subprocess
import sys

import lpad.color as col

# Patterns for Launchpad source package remote URLs
# e.g. git+ssh://git.launchpad.net/~user/ubuntu/+source/curl
#      https://git.launchpad.net/~user/ubuntu/+source/curl
#      git+ssh://git.launchpad.net/ubuntu/+source/curl  (team-less)
_SOURCE_PKG_RE = re.compile(r"git\.launchpad\.net/(?:[^/]+/)*\+source/([^/\s]+)")


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
        col.info("Could not detect source package from git remote."),
        file=sys.stderr,
    )
    pkg = input(col.prompt("Enter source package name: ")).strip()
    if not pkg:
        print(col.error("Error: source package name cannot be empty."), file=sys.stderr)
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
    """Parse a bug number from a branch name.

    Recognised forms (all case-sensitive on the literal segments):

    - ``lp1234567-fix-crash``
    - ``noble-lp1234567-fix-crash``
    - ``noble-sru-lp1234567-fix-crash``
    - ``merge-lp1234567-noble``

    Returns the bug number as an int, or None if the branch doesn't match.
    """
    m = re.match(r"^(?:[a-z]+-)*(?:sru-)?lp(\d+)", branch)
    if m:
        return int(m.group(1))
    return None


def parse_changelog_series(path: str = "debian/changelog") -> str | None:
    """Extract the target series from the top entry of a Debian changelog.

    Looks for the distribution field in the first stanza, e.g.:
        curl (8.5.0-2ubuntu1) noble; urgency=medium
    Returns 'noble', or None if the file is missing or unparseable.
    """
    # Resolve relative to the git repo root so this works regardless of cwd
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            capture_output=True,
            text=True,
            check=True,
        )
        repo_root = result.stdout.strip()
    except subprocess.CalledProcessError:
        return None

    changelog_path = os.path.join(repo_root, path)
    try:
        with open(changelog_path, encoding="utf-8", errors="replace") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                # Debian changelog first line format:
                #   package (version) distribution; urgency=...
                #   [ Some Team ]                    ← optional team header, skip
                if line.startswith("["):
                    continue
                # Find the closing parenthesis of the version
                if "(" in line and ")" in line:
                    after_version = line.split(")", 1)[1]
                    parts = after_version.split(";")
                    if parts:
                        dist = parts[0].strip()
                        if dist:
                            return dist
                break
    except FileNotFoundError:
        pass
    except Exception:
        pass
    return None
