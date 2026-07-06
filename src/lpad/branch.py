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


def _check_clean_worktree() -> None:
    """Abort with a clear error if the git working tree is dirty."""
    try:
        result = subprocess.run(
            ["git", "status", "--porcelain"],
            capture_output=True,
            text=True,
            check=True,
        )
    except subprocess.CalledProcessError:
        print(
            col.error("Error: not inside a git repository."),
            file=sys.stderr,
        )
        sys.exit(1)
    if result.stdout.strip():
        print(
            col.error(
                "Error: working tree is not clean. "
                "Commit or stash your changes before creating a branch."
            ),
            file=sys.stderr,
        )
        sys.exit(1)


def create_branch(
    bug_id: int,
    series: str | None = None,
    kind: str = "normal",
) -> None:
    """Prompt for a description and create a git branch for *bug_id*.

    Branch naming depends on *kind*:

    - ``"normal"`` (default): ``lp<id>-<slug>`` or ``<series>-lp<id>-<slug>``
      when *series* is given.
    - ``"sru"``: ``<series>-sru-lp<id>-<slug>``. *series* must be provided
      (caller is responsible for resolving it).
    - ``"merge"``: ``merge-lp<id>-<series>``. No description is prompted;
      *series* must be provided.

    Exits with an error if not in a git repository or if git checkout fails.
    """
    if kind == "merge":
        if not series:
            print(
                col.error("Error: --merge requires a release (use --series)."),
                file=sys.stderr,
            )
            sys.exit(1)
        branch_name = f"merge-lp{bug_id}-{series}"
    else:
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

        if kind == "sru":
            if not series:
                print(
                    col.error("Error: --sru requires a release (use --series)."),
                    file=sys.stderr,
                )
                sys.exit(1)
            branch_name = f"{series}-sru-lp{bug_id}-{slug}"
        elif kind == "normal":
            branch_name = f"{series}-lp{bug_id}-{slug}" if series else f"lp{bug_id}-{slug}"
        else:
            print(
                col.error(f"Error: unknown branch kind '{kind}'."),
                file=sys.stderr,
            )
            sys.exit(1)

    _check_clean_worktree()

    try:
        subprocess.run(
            ["git", "checkout", "-b", branch_name],
            check=True,
        )
        print(col.success("Created and switched to branch: ") + col.branch_name(branch_name))
    except subprocess.CalledProcessError:
        print(
            col.error(
                f"Error: failed to create branch '{branch_name}'. "
                "Is there already a branch with this name?"
            ),
            file=sys.stderr,
        )
        sys.exit(1)
