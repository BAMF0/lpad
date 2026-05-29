"""Bug operations against the Launchpad API."""

import shutil
import subprocess
import sys
import textwrap
import webbrowser
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from launchpadlib.launchpad import Launchpad

LAUNCHPAD_BUG_URL = "https://bugs.launchpad.net/bugs/{bug_id}"


@dataclass
class BugSummary:
    id: int
    title: str
    status: str
    importance: str
    assignee: str | None
    tags: list[str] = field(default_factory=list)

    def fzf_line(self) -> str:
        assignee = self.assignee or "unassigned"
        return (
            f"#{self.id:<10} [{self.status:<13}] "
            f"{self.importance:<10} {self.title}  ({assignee})"
        )


def _check_fzf() -> None:
    """Exit with a clear error if fzf is not installed."""
    result = subprocess.run(["which", "fzf"], capture_output=True)
    if result.returncode != 0:
        print(
            "Error: fzf is not installed.\n"
            "Install it with:  sudo apt install fzf\n"
            "or visit:         https://github.com/junegunn/fzf",
            file=sys.stderr,
        )
        sys.exit(1)


def _get_source_package(lp: "Launchpad", package_name: str):
    """Return the Launchpad source package object for Ubuntu."""
    ubuntu = lp.distributions["ubuntu"]
    series = ubuntu.current_series
    return series.getSourcePackage(name=package_name)


def get_package_bugs(
    lp: "Launchpad",
    package_name: str,
    force_refresh: bool = False,
) -> list[BugSummary]:
    """Return all bugs for the given Ubuntu source package.

    Results are loaded from a local cache (~/.cache/lpad/<package>.json) when
    available and fresh. Pass force_refresh=True (or run `lpad sync`) to
    bypass the cache and fetch from Launchpad.
    """
    from lpad.cache import cache_info, load_cache, save_cache

    if not force_refresh:
        cached = load_cache(package_name)
        if cached is not None:
            info = cache_info(package_name)
            print(f"Using cached bugs ({info}).", file=sys.stderr)
            return cached

    print(f"Fetching bugs for {package_name} from Launchpad...", file=sys.stderr)
    ubuntu = lp.distributions["ubuntu"]
    spkg = ubuntu.getSourcePackage(name=package_name)
    bugs = []
    for task in spkg.searchTasks():
        bug = task.bug
        assignee = None
        if task.assignee:
            try:
                assignee = task.assignee.display_name
            except Exception:
                pass
        try:
            tags = list(bug.tags)
        except Exception:
            tags = []
        bugs.append(
            BugSummary(
                id=bug.id,
                title=bug.title,
                status=task.status,
                importance=task.importance,
                assignee=assignee,
                tags=tags,
            )
        )
    save_cache(package_name, bugs)
    return bugs


def fzf_select_bug(bugs: list[BugSummary]) -> BugSummary | None:
    """Present bugs in fzf with a live preview panel and return the selected one."""
    _check_fzf()
    if not bugs:
        print("No bugs found.", file=sys.stderr)
        return None

    lines = [b.fzf_line() for b in bugs]
    input_text = "\n".join(lines)

    result = subprocess.run(
        [
            "fzf",
            "--ansi",
            "--prompt=Select bug> ",
            "--height=80%",
            "--reverse",
            "--preview=lpad _preview {1}",
            "--preview-window=right:50%:wrap",
        ],
        input=input_text,
        capture_output=True,
        text=True,
    )

    if result.returncode != 0 or not result.stdout.strip():
        return None

    selected_line = result.stdout.strip()
    # Extract bug ID from the start of the line: #<id>
    try:
        bug_id = int(selected_line.split()[0].lstrip("#"))
    except (IndexError, ValueError):
        return None

    for bug in bugs:
        if bug.id == bug_id:
            return bug
    return None


def print_bug_summary(bug: BugSummary) -> None:
    """Print a compact overview from a cached BugSummary — no API calls."""
    url = LAUNCHPAD_BUG_URL.format(bug_id=bug.id)
    print(f"Bug #{bug.id}: {bug.title}")
    print(f"  URL:        {url}")
    print(f"  Status:     {bug.status}")
    print(f"  Importance: {bug.importance}")
    print(f"  Assignee:   {bug.assignee or 'unassigned'}")
    print(f"  Tags:       {', '.join(bug.tags) if bug.tags else 'none'}")


def get_bug_by_id(lp: "Launchpad", bug_id: int) -> "object":
    """Return a Launchpad bug object by ID."""
    return lp.bugs[bug_id]


def print_bug_status(
    lp: "Launchpad",
    bug_id: int,
    package_name: str,
    verbose: bool = False,
) -> None:
    """Print a live status summary for the given bug via the Launchpad API.

    When verbose=True, also prints the bug heat and full description,
    word-wrapped to the current terminal width.
    """
    bug = get_bug_by_id(lp, bug_id)

    task_info = None
    for task in bug.bug_tasks:
        target_name = task.bug_target_name
        if package_name in target_name or "ubuntu" in target_name.lower():
            assignee = None
            if task.assignee:
                try:
                    assignee = task.assignee.display_name
                except Exception:
                    pass
            task_info = {
                "status": task.status,
                "importance": task.importance,
                "assignee": assignee or "unassigned",
                "target": target_name,
            }
            break

    print(f"Bug #{bug_id}: {bug.title}")
    print(f"  URL:        {LAUNCHPAD_BUG_URL.format(bug_id=bug_id)}")
    if task_info:
        print(f"  Target:     {task_info['target']}")
        print(f"  Status:     {task_info['status']}")
        print(f"  Importance: {task_info['importance']}")
        print(f"  Assignee:   {task_info['assignee']}")
    print(f"  Tags:       {', '.join(bug.tags) if bug.tags else 'none'}")

    if verbose:
        print(f"  Heat:       {bug.heat}")
        description = bug.description or "(no description)"
        term_width = shutil.get_terminal_size().columns
        # Reserve 4 characters for the leading indent
        wrapped = textwrap.fill(
            description,
            width=max(40, term_width - 4),
            initial_indent="    ",
            subsequent_indent="    ",
        )
        print(f"  Description:\n{wrapped}")


def open_bug_in_browser(bug_id: int) -> None:
    """Open the given bug in the default web browser."""
    url = LAUNCHPAD_BUG_URL.format(bug_id=bug_id)
    print(f"Opening {url}")
    webbrowser.open(url)


def report_bug(lp: "Launchpad", package_name: str) -> None:
    """Interactively file a new bug against the given Ubuntu source package."""
    print(f"Reporting bug against: {package_name} (Ubuntu)")
    title = input("Title: ").strip()
    if not title:
        print("Error: title cannot be empty.", file=sys.stderr)
        sys.exit(1)

    print("Description (press Ctrl+D on an empty line when done):")
    lines = []
    try:
        while True:
            line = input()
            lines.append(line)
    except EOFError:
        pass
    description = "\n".join(lines).strip()
    if not description:
        print("Error: description cannot be empty.", file=sys.stderr)
        sys.exit(1)

    ubuntu = lp.distributions["ubuntu"]
    spkg = ubuntu.getSourcePackage(name=package_name)
    bug = lp.bugs.createBug(
        target=spkg,
        title=title,
        description=description,
    )
    print(f"Bug #{bug.id} created: {LAUNCHPAD_BUG_URL.format(bug_id=bug.id)}")


def subscribe_to_bug(lp: "Launchpad", bug_id: int) -> None:
    """Subscribe the authenticated user to the given bug."""
    bug = get_bug_by_id(lp, bug_id)
    me = lp.me
    bug.subscribe(person=me)
    print(f"Subscribed to bug #{bug_id}: {bug.title}")
