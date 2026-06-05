"""Git branch creation for Launchpad bugs."""

import re
import subprocess
import sys

import lpad.color as col


def _slugify(text: str) -> str:
    """Convert a description string to a branch-safe slug.

    Lowercases, replaces whitespace and underscores with hyphens,
    strips non-alphanumeric characters, and collapses multiple hyphens.
    """
    text = text.lower().strip()
    text = re.sub(r"[\s_]+", "-", text)
    text = re.sub(r"[^a-z0-9-]", "", text)
    text = re.sub(r"-{2,}", "-", text)
    return text.strip("-")


def create_branch(bug_id: int) -> None:
    """Prompt for a description and create a git branch lp<bug_id>-<desc>.

    Exits with an error if not in a git repository or if git checkout fails.
    """
    raw_desc = input(
        col.prompt("Branch description (short, e.g. 'fix crash on startup'): ")
    ).strip()
    if not raw_desc:
        print(col.error("Error: description cannot be empty."), file=sys.stderr)
        sys.exit(1)

    slug = _slugify(raw_desc)
    if not slug:
        print(
            col.error("Error: description produced an empty slug after sanitization."),
            file=sys.stderr,
        )
        sys.exit(1)

    branch_name = f"lp{bug_id}-{slug}"

    try:
        subprocess.run(
            ["git", "checkout", "-b", branch_name],
            check=True,
        )
        print(
            col.success("Created and switched to branch: ")
            + col.branch_name(branch_name)
        )
    except subprocess.CalledProcessError:
        print(
            col.error(
                f"Error: failed to create branch '{branch_name}'. "
                "Is there already a branch with this name?"
            ),
            file=sys.stderr,
        )
        sys.exit(1)
