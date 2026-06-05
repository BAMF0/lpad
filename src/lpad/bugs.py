"""Bug operations against the Launchpad API."""

import shutil
import subprocess
import sys
import textwrap
import webbrowser
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

import lpad.color as col

if TYPE_CHECKING:
    from launchpadlib.launchpad import Launchpad

LAUNCHPAD_BUG_URL = "https://bugs.launchpad.net/bugs/{bug_id}"


@dataclass
class Comment:
    index: int    # 1-based; message[0] (the description) is skipped
    author: str
    date: str     # ISO 8601 string as returned by Launchpad
    body: str


@dataclass
class BugWatch:
    url: str
    title: str             # e.g. "Debian Bug tracker #1234567"
    remote_bug: str        # bug number/ID in the external tracker
    remote_status: str     # raw status string from the remote tracker
    remote_importance: str
    date_last_changed: str | None   # ISO 8601, or None if unavailable


@dataclass
class BugSummary:
    id: int
    title: str
    status: str
    importance: str
    assignee: str | None
    tags: list[str] = field(default_factory=list)
    watches: list[BugWatch] = field(default_factory=list)

    def fzf_line(self) -> str:
        assignee_str = col.c(
            f"({self.assignee or 'unassigned'})", col.DIM
        )
        return (
            f"{col.bug_id(f'#{self.id}'):<20} "
            f"[{col.status_color(f'{self.status}'):<24}] "
            f"{col.importance_color(f'{self.importance}'):<20} "
            f"{self.title}  {assignee_str}"
        )


def _check_fzf() -> None:
    """Exit with a clear error if fzf is not installed."""
    result = subprocess.run(["which", "fzf"], capture_output=True)
    if result.returncode != 0:
        print(
            col.error(
                "Error: fzf is not installed.\n"
                "Install it with:  sudo apt install fzf\n"
                "or visit:         https://github.com/junegunn/fzf"
            ),
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
            print(col.info(f"Using cached bugs ({info})."), file=sys.stderr)
            return cached

    print(
        col.info(f"Fetching bugs for {package_name} from Launchpad..."),
        file=sys.stderr,
    )
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
        try:
            watches = _fetch_watches(bug)
        except Exception:
            watches = []
        bugs.append(
            BugSummary(
                id=bug.id,
                title=bug.title,
                status=task.status,
                importance=task.importance,
                assignee=assignee,
                tags=tags,
                watches=watches,
            )
        )
    save_cache(package_name, bugs)
    return bugs


def _fetch_watches(bug) -> list["BugWatch"]:
    """Return a list of BugWatch for a launchpadlib bug object.

    Each attribute access on a watch may raise; individual failures are
    silently ignored so the parent bug is never dropped.
    """
    watches = []
    for watch in bug.bug_watches:
        try:
            date_lc = str(watch.date_last_changed) if watch.date_last_changed else None
        except Exception:
            date_lc = None
        try:
            watches.append(BugWatch(
                url=watch.url or "",
                title=watch.title or "",
                remote_bug=str(watch.remote_bug) if watch.remote_bug else "",
                remote_status=watch.remote_status or "",
                remote_importance=watch.remote_importance or "",
                date_last_changed=date_lc,
            ))
        except Exception:
            continue
    return watches


def fzf_select_bug(bugs: list[BugSummary]) -> BugSummary | None:
    """Present bugs in fzf with a live preview panel and return the selected one."""
    _check_fzf()
    if not bugs:
        print(col.info("No bugs found."), file=sys.stderr)
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
    # Extract bug ID from the start of the line, stripping ANSI codes first
    raw = selected_line.split()[0]
    # Strip ANSI escape sequences then the leading '#'
    import re
    raw = re.sub(r"\033\[[0-9;]*m", "", raw).lstrip("#")
    try:
        bug_id = int(raw)
    except (IndexError, ValueError):
        return None

    for bug in bugs:
        if bug.id == bug_id:
            return bug
    return None


def _print_bug_header(bug_id: int, bug_title: str) -> None:
    print(f"{col.bug_id(f'Bug #{bug_id}')}: {col.title(bug_title)}")


def _print_bug_fields(
    bug_url: str,
    status: str,
    importance: str,
    assignee_str: str,
    tags_list: list[str],
    target: str | None = None,
) -> None:
    lbl = col.label
    print(f"  {lbl('URL:'):<20} {col.url(bug_url)}")
    if target:
        print(f"  {lbl('Target:'):<20} {target}")
    print(f"  {lbl('Status:'):<20} {col.status_color(status)}")
    print(f"  {lbl('Importance:'):<20} {col.importance_color(importance)}")
    print(f"  {lbl('Assignee:'):<20} {col.assignee(assignee_str)}")
    tags_str = (
        col.tags(", ".join(tags_list)) if tags_list else col.info("none")
    )
    print(f"  {lbl('Tags:'):<20} {tags_str}")


def _print_bug_watches(watches: list[BugWatch]) -> None:
    """Print the remote bug watches section."""
    lbl = col.label
    if not watches:
        print(f"  {lbl('Remote Watches:'):<20} {col.info('none')}")
        return

    print(f"  {lbl('Remote Watches:'):<20} {col.info(f'({len(watches)})')}")
    for w in watches:
        print(f"    {col.title(w.title)}")
        print(f"      {lbl('URL:'):<18} {col.url(w.url)}")
        if w.remote_status:
            print(f"      {lbl('Status:'):<18} {w.remote_status}")
        if w.remote_importance:
            print(f"      {lbl('Importance:'):<18} {w.remote_importance}")
        if w.date_last_changed:
            try:
                from datetime import datetime, timezone
                dt = datetime.fromisoformat(w.date_last_changed)
                dt = dt.astimezone(timezone.utc)
                date_str = dt.strftime("%Y-%m-%d %H:%M UTC")
            except Exception:
                date_str = w.date_last_changed
            print(f"      {lbl('Last changed:'):<18} {col.info(date_str)}")


def print_bug_summary(bug: BugSummary) -> None:
    """Print a compact overview from a cached BugSummary — no API calls."""
    _print_bug_header(bug.id, bug.title)
    _print_bug_fields(
        bug_url=LAUNCHPAD_BUG_URL.format(bug_id=bug.id),
        status=bug.status,
        importance=bug.importance,
        assignee_str=bug.assignee or "unassigned",
        tags_list=bug.tags,
    )
    _print_bug_watches(bug.watches)


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

    _print_bug_header(bug_id, bug.title)
    _print_bug_fields(
        bug_url=LAUNCHPAD_BUG_URL.format(bug_id=bug_id),
        status=task_info["status"] if task_info else bug.status,
        importance=task_info["importance"] if task_info else "Undecided",
        assignee_str=task_info["assignee"] if task_info else "unassigned",
        tags_list=list(bug.tags),
        target=task_info["target"] if task_info else None,
    )
    try:
        watches = _fetch_watches(bug)
    except Exception:
        watches = []
    _print_bug_watches(watches)

    if verbose:
        lbl = col.label
        print(f"  {lbl('Heat:'):<20} {bug.heat}")
        description = bug.description or "(no description)"
        term_width = shutil.get_terminal_size().columns
        wrap_width = max(40, term_width - 4)
        indent = "    "
        print(f"  {lbl('Description:')}")
        for line in description.splitlines():
            if line.strip() == "":
                print()
            elif line[0].isspace():
                # Preformatted / indented content — preserve as-is, dimmed
                print(col.c(indent + line, col.DIM))
            else:
                print(textwrap.fill(
                    line,
                    width=wrap_width,
                    initial_indent=indent,
                    subsequent_indent=indent,
                ))


def open_bug_in_browser(bug_id: int) -> None:
    """Open the given bug in the default web browser."""
    bug_url = LAUNCHPAD_BUG_URL.format(bug_id=bug_id)
    print(col.info("Opening ") + col.url(bug_url))
    webbrowser.open(bug_url)


def report_bug(lp: "Launchpad", package_name: str) -> None:
    """Interactively file a new bug against the given Ubuntu source package."""
    print(col.info(f"Reporting bug against: {package_name} (Ubuntu)"))
    raw_title = input(col.prompt("Title: ")).strip()
    if not raw_title:
        print(col.error("Error: title cannot be empty."), file=sys.stderr)
        sys.exit(1)

    print(col.prompt("Description") + col.info(" (press Ctrl+D when done):"))
    lines = []
    try:
        while True:
            lines.append(input())
    except EOFError:
        pass
    description = "\n".join(lines).strip()
    if not description:
        print(col.error("Error: description cannot be empty."), file=sys.stderr)
        sys.exit(1)

    ubuntu = lp.distributions["ubuntu"]
    spkg = ubuntu.getSourcePackage(name=package_name)
    bug = lp.bugs.createBug(
        target=spkg,
        title=raw_title,
        description=description,
    )
    bug_url = LAUNCHPAD_BUG_URL.format(bug_id=bug.id)
    print(
        col.success(f"Bug #{bug.id} created: ") + col.url(bug_url)
    )


def subscribe_to_bug(lp: "Launchpad", bug_id: int) -> None:
    """Subscribe the authenticated user to the given bug."""
    bug = get_bug_by_id(lp, bug_id)
    me = lp.me
    bug.subscribe(person=me)
    print(col.success(f"Subscribed to bug #{bug_id}: {bug.title}"))


def get_bug_comments(
    lp: "Launchpad",
    bug_id: int,
    force_refresh: bool = False,
) -> list[Comment]:
    """Return all comments for the given bug.

    Results are loaded from ~/.cache/lpad/comments/<bug_id>.json when
    available and fresh. Pass force_refresh=True to bypass the cache.
    message[0] is the bug description and is skipped.
    """
    from lpad.cache import comment_cache_info, load_comment_cache, save_comment_cache

    if not force_refresh:
        cached = load_comment_cache(bug_id)
        if cached is not None:
            info = comment_cache_info(bug_id)
            print(col.info(f"Using cached comments ({info})."), file=sys.stderr)
            return cached

    print(col.info(f"Fetching comments for bug #{bug_id} from Launchpad..."), file=sys.stderr)
    bug = get_bug_by_id(lp, bug_id)
    comments = []
    for i, message in enumerate(bug.messages):
        if i == 0:
            # message[0] is the bug description, not a comment
            continue
        try:
            author = message.owner.display_name
        except Exception:
            author = "(unknown)"
        comments.append(Comment(
            index=i,
            author=author,
            date=str(message.date_created),
            body=message.content or "",
        ))
    save_comment_cache(bug_id, comments)
    return comments


def _format_comment_date(iso_date: str) -> str:
    """Return a short human-readable date from an ISO 8601 string."""
    try:
        from datetime import datetime, timezone
        dt = datetime.fromisoformat(iso_date)
        dt = dt.astimezone(timezone.utc)
        return dt.strftime("%Y-%m-%d %H:%M UTC")
    except Exception:
        return iso_date


def _print_body(body: str, term_width: int) -> None:
    """Print a comment or description body with word-wrap and preformatted-line support."""
    indent = "  "
    wrap_width = max(40, term_width - len(indent))
    for line in body.splitlines():
        if line.strip() == "":
            print()
        elif line[0].isspace():
            # Preserve intentionally indented content (stack traces, etc.)
            print(col.c(indent + line, col.DIM))
        else:
            print(textwrap.fill(
                line,
                width=wrap_width,
                initial_indent=indent,
                subsequent_indent=indent,
            ))


def print_comments(
    comments: list[Comment],
    first: int | None = None,
    last: int | None = None,
    reverse: bool = False,
) -> None:
    """Print bug comments with optional filtering and ordering.

    Args:
        comments: Full list of comments (oldest first).
        first:    If set, show only the first N comments.
        last:     If set, show only the last N comments.
        reverse:  If True, display newest first.
    """
    if not comments:
        print(col.info("No comments on this bug."))
        return

    # Apply first/last slicing before reversing
    if first is not None:
        subset = comments[:first]
    elif last is not None:
        subset = comments[-last:]
    else:
        subset = list(comments)

    if reverse:
        subset = list(reversed(subset))

    term_width = shutil.get_terminal_size().columns
    sep_char = "─"

    for i, comment in enumerate(subset):
        date_str = _format_comment_date(comment.date)
        # Build the header: ── Comment #N by Author  ·  date ──────
        header_text = (
            f" Comment {col.c(f'#{comment.index}', col.BOLD)} "
            f"by {col.assignee(comment.author)}  "
            f"{col.c('·', col.DIM)}  {col.c(date_str, col.DIM)} "
        )
        # Strip ANSI codes to measure printable width for the trailing dashes
        import re
        plain_header = re.sub(r"\033\[[0-9;]*m", "", header_text)
        trail_len = max(0, term_width - len(plain_header) - 2)
        separator = (
            col.c(sep_char * 2, col.DIM)
            + header_text
            + col.c(sep_char * trail_len, col.DIM)
        )
        print(separator)
        _print_body(comment.body, term_width)
        if i < len(subset) - 1:
            print()
