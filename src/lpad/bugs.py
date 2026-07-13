"""Bug operations against the Launchpad API."""

import contextlib
import re
import shutil
import subprocess
import sys
import textwrap
import webbrowser
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

import lpad.color as col

if TYPE_CHECKING:
    from launchpadlib.launchpad import Launchpad

LAUNCHPAD_BUG_URL = "https://bugs.launchpad.net/bugs/{bug_id}"

# Statuses considered "open" — used as the default filter for
# get_package_bugs() so closed bugs don't drown out the active set.
OPEN_STATUSES = [
    "New",
    "Incomplete",
    "Confirmed",
    "Triaged",
    "In Progress",
    "Fix Committed",
]

_ANSI_RE = re.compile(r"\033\[[0-9;]*m")


def _strip_ansi(text: str) -> str:
    """Remove ANSI escape sequences from *text*."""
    return _ANSI_RE.sub("", text)


def _truncate_ansi(text: str, max_width: int) -> str:
    """Truncate *text* (which may contain ANSI codes) to *max_width* visible chars.

    Appends an ellipsis when truncation occurs. ANSI escapes are not
    counted toward the visible width.
    """
    if max_width <= 0:
        return ""
    plain = _strip_ansi(text)
    if len(plain) <= max_width:
        return text
    # Walk the original string, counting only non-escape characters,
    # until we have consumed (max_width - 1) visible chars; then append "…".
    visible = 0
    out: list[str] = []
    i = 0
    ellipsis = "…"
    target = max_width - 1
    while i < len(text) and visible < target:
        match = _ANSI_RE.match(text, i)
        if match:
            out.append(match.group(0))
            i = match.end()
            continue
        out.append(text[i])
        visible += 1
        i += 1
    out.append(ellipsis)
    return "".join(out)


@dataclass
class Comment:
    index: int  # 1-based; message[0] (the description) is skipped
    author: str
    date: str  # ISO 8601 string as returned by Launchpad
    body: str


@dataclass
class BugWatch:
    url: str
    title: str  # e.g. "Debian Bug tracker #1234567"
    remote_bug: str  # bug number/ID in the external tracker
    remote_status: str  # raw status string from the remote tracker
    remote_importance: str
    date_last_changed: str | None  # ISO 8601, or None if unavailable


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
        # Tightened fixed columns so the title gets room even on
        # narrow terminals. On very narrow widths the assignee is
        # dropped and the title is truncated to fit.
        id_part = col.bug_id(f"#{self.id}")
        status_part = col.status_color(f"{self.status}")
        importance_part = col.importance_color(f"{self.importance}")
        prefix = f"{id_part:<10} [{status_part:<16}] {importance_part:<10} "

        prefix_plain = _strip_ansi(prefix)
        assignee_str = self.assignee or "unassigned"
        assignee_col = col.c(f"({assignee_str})", col.DIM)
        assignee_plain = _strip_ansi(assignee_col)

        # fzf gives the list ~60% of the terminal (preview takes 40%).
        term_width = shutil.get_terminal_size().columns
        list_width = max(40, int(term_width * 0.6))
        available = list_width - len(prefix_plain)

        if available - len(assignee_plain) - 1 < 20:
            # Narrow: drop the assignee, give the title all the room.
            title = _truncate_ansi(self.title, max(8, available))
            return f"{prefix}{title}"
        title = _truncate_ansi(self.title, max(8, available - len(assignee_plain) - 2))
        return f"{prefix}{title}  {assignee_col}"


def _check_fzf() -> None:
    """Exit with a clear error if fzf is not installed."""
    if not shutil.which("fzf"):
        print(
            col.error(
                "Error: fzf is not installed.\n"
                "Install it with:  sudo apt install fzf\n"
                "or visit:         https://github.com/junegunn/fzf"
            ),
            file=sys.stderr,
        )
        sys.exit(1)


def _get_source_package(lp: "Launchpad", package_name: str) -> Any:
    """Return the Launchpad source package object for Ubuntu."""
    ubuntu = lp.distributions["ubuntu"]
    series = ubuntu.current_series
    return series.getSourcePackage(name=package_name)


def get_package_bugs(
    lp: "Launchpad",
    package_name: str,
    force_refresh: bool = False,
    status: list[str] | None = OPEN_STATUSES,
) -> list[BugSummary]:
    """Return bugs for the given Ubuntu source package.

    Results are loaded from a local cache (~/.cache/lpad/<package>.json) when
    available and fresh. Pass force_refresh=True (or run `lpad sync`) to
    bypass the cache and fetch from Launchpad.

    By default only open bugs are returned (see OPEN_STATUSES). Pass
    status=None to fetch all statuses, or a custom list to filter.
    """
    from lpad.cache import cache_info, load_cache, save_cache

    if not force_refresh:
        cached = load_cache(package_name, status_filter=status)
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
    search_kwargs: dict[str, object] = {}
    if status:
        search_kwargs["status"] = status
    bugs = []
    for task in spkg.searchTasks(**search_kwargs):
        bug = task.bug
        assignee = None
        if task.assignee:
            with contextlib.suppress(Exception):
                assignee = task.assignee.display_name
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
    save_cache(package_name, bugs, status_filter=status)
    return bugs


def _fetch_watches(bug: Any) -> list["BugWatch"]:
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
            watches.append(
                BugWatch(
                    url=watch.url or "",
                    title=watch.title or "",
                    remote_bug=str(watch.remote_bug) if watch.remote_bug else "",
                    remote_status=watch.remote_status or "",
                    remote_importance=watch.remote_importance or "",
                    date_last_changed=date_lc,
                )
            )
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
            "--preview-window=right:40%:wrap",
        ],
        input=input_text,
        capture_output=True,
        text=True,
    )

    if result.returncode != 0 or not result.stdout.strip():
        return None

    selected_line = result.stdout.strip()
    if not selected_line:
        return None
    # Extract bug ID from the start of the line, stripping ANSI codes first
    raw = selected_line.split()[0]
    raw = _strip_ansi(raw).lstrip("#")
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
    tags_str = col.tags(", ".join(tags_list)) if tags_list else col.info("none")
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
                dt = datetime.fromisoformat(w.date_last_changed)
                dt = dt.astimezone(UTC)
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


def print_package_dashboard(
    package: str,
    bugs: list[BugSummary],
    cache_info_str: str | None = None,
) -> None:
    """Print a read-only overview of bugs for a source package.

    Pure function: no API calls, no cache I/O — receives already-fetched
    data. Shows total count, breakdowns by status/importance, top
    assignees, and the number of bugs carrying remote watches.
    """
    from collections import Counter

    lbl = col.label

    print(f"{col.title(package)}  ", end="")
    if cache_info_str:
        print(col.info(f"({cache_info_str})"))
    else:
        print()

    if not bugs:
        print(col.info("No bugs in cache for this package."))
        return

    print(f"  {lbl('Total bugs:'):<20} {len(bugs)}")

    # Status breakdown
    status_counts = Counter(b.status for b in bugs)
    print(f"  {lbl('By status:'):<20}")
    for status, count in status_counts.most_common():
        print(f"    {col.status_color(status):<24} {count}")

    # Importance breakdown
    importance_counts = Counter(b.importance for b in bugs)
    print(f"  {lbl('By importance:'):<20}")
    for importance, count in importance_counts.most_common():
        print(f"    {col.importance_color(importance):<24} {count}")

    # Top assignees
    assignee_counts = Counter(b.assignee or "unassigned" for b in bugs)
    top_n = 5
    print(f"  {lbl(f'Top assignees (of {len(assignee_counts)}):'):<20}")
    for assignee, count in assignee_counts.most_common(top_n):
        print(f"    {col.assignee(assignee):<24} {count}")

    # Bugs with remote watches
    with_watches = sum(1 for b in bugs if b.watches)
    print(f"  {lbl('With remote watches:'):<20} {with_watches}")


def get_bug_by_id(lp: "Launchpad", bug_id: int) -> Any:
    """Return a Launchpad bug object by ID.

    Exits with a clear error if the bug does not exist, is private, or the
    API call fails for any other reason.
    """
    try:
        return lp.bugs[bug_id]
    except KeyError:
        print(
            col.error(f"Error: bug #{bug_id} not found on Launchpad."),
            file=sys.stderr,
        )
        sys.exit(1)
    except Exception as exc:
        print(
            col.error(f"Error: could not fetch bug #{bug_id} from Launchpad: {exc}"),
            file=sys.stderr,
        )
        sys.exit(1)


def print_bug_status(
    lp: "Launchpad",
    bug_id: int,
    package_name: str | None = None,
    verbose: bool = False,
) -> None:
    """Print a live status summary for the given bug via the Launchpad API.

    When *package_name* is given, the Ubuntu task for that package is
    matched and its status/importance/assignee are shown. When None, only
    bug-level fields are displayed (useful when called outside a source
    tree without -p).

    When verbose=True, also prints the bug heat and full description,
    word-wrapped to the current terminal width.
    """
    bug = get_bug_by_id(lp, bug_id)

    task_info = None
    if package_name:
        # Preferred task target names for an Ubuntu source package.
        canonical_targets = {
            f"{package_name} (Ubuntu)",
            f"{package_name} (Ubuntu {package_name})",
        }
        for task in bug.bug_tasks:
            try:
                target_name = task.bug_target_name
            except Exception:
                continue
            if target_name in canonical_targets or (
                target_name == package_name
                or (package_name in target_name and "ubuntu" in target_name.lower())
            ):
                assignee = None
                try:
                    if task.assignee:
                        assignee = task.assignee.display_name
                except Exception:
                    pass
                try:
                    status = task.status
                except Exception:
                    status = "(unknown)"
                try:
                    importance = task.importance
                except Exception:
                    importance = "Undecided"
                task_info = {
                    "status": status,
                    "importance": importance,
                    "assignee": assignee or "unassigned",
                    "target": target_name,
                }
                break

    try:
        title = bug.title
    except Exception:
        title = "(unavailable)"
    _print_bug_header(bug_id, title)
    try:
        bug_status = bug.status
    except Exception:
        bug_status = "(unknown)"
    _print_bug_fields(
        bug_url=LAUNCHPAD_BUG_URL.format(bug_id=bug_id),
        status=task_info["status"] if task_info else bug_status,
        importance=task_info["importance"] if task_info else "Undecided",
        assignee_str=task_info["assignee"] if task_info else "unassigned",
        tags_list=_safe_tags(bug),
        target=task_info["target"] if task_info else None,
    )
    try:
        watches = _fetch_watches(bug)
    except Exception:
        watches = []
    _print_bug_watches(watches)

    if verbose:
        lbl = col.label
        try:
            heat = bug.heat
        except Exception:
            heat = "(unavailable)"
        print(f"  {lbl('Heat:'):<20} {heat}")
        try:
            description = bug.description or "(no description)"
        except Exception:
            description = "(no description)"
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
                print(
                    textwrap.fill(
                        line,
                        width=wrap_width,
                        initial_indent=indent,
                        subsequent_indent=indent,
                    )
                )


def _safe_tags(bug: Any) -> list[str]:
    """Return bug.tags defensively, never raising."""
    try:
        return list(bug.tags)
    except Exception:
        return []


def open_bug_in_browser(bug_id: int) -> None:
    """Open the given bug in the default web browser."""
    bug_url = LAUNCHPAD_BUG_URL.format(bug_id=bug_id)
    print(col.info("Opening ") + col.url(bug_url))
    webbrowser.open(bug_url)


def report_bug(lp: "Launchpad", package_name: str) -> int:
    """Interactively file a new bug against the given Ubuntu source package.

    Returns the new bug ID on success. Exits with a clear error on failure.
    """
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
    try:
        bug = lp.bugs.createBug(
            target=spkg,
            title=raw_title,
            description=description,
        )
    except Exception as exc:
        print(
            col.error(f"Error: failed to create bug on Launchpad: {exc}"),
            file=sys.stderr,
        )
        sys.exit(1)
    bug_url = LAUNCHPAD_BUG_URL.format(bug_id=bug.id)
    print(col.success(f"Bug #{bug.id} created: ") + col.url(bug_url))
    return int(bug.id)


def subscribe_to_bug(lp: "Launchpad", bug_id: int) -> None:
    """Subscribe the authenticated user to the given bug."""
    bug = get_bug_by_id(lp, bug_id)
    me = lp.me
    try:
        bug.subscribe(person=me)
    except Exception as exc:
        print(
            col.error(f"Error: could not subscribe to bug #{bug_id}: {exc}"),
            file=sys.stderr,
        )
        sys.exit(1)
    try:
        title = bug.title
    except Exception:
        title = "(unavailable)"
    print(col.success(f"Subscribed to bug #{bug_id}: {title}"))


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
        comments.append(
            Comment(
                index=i,
                author=author,
                date=str(message.date_created),
                body=message.content or "",
            )
        )
    save_comment_cache(bug_id, comments)
    return comments


def _format_comment_date(iso_date: str) -> str:
    """Return a short human-readable date from an ISO 8601 string."""
    try:
        dt = datetime.fromisoformat(iso_date)
        dt = dt.astimezone(UTC)
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
            print(
                textwrap.fill(
                    line,
                    width=wrap_width,
                    initial_indent=indent,
                    subsequent_indent=indent,
                )
            )


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
        plain_header = _strip_ansi(header_text)
        trail_len = max(0, term_width - len(plain_header) - 2)
        separator = (
            col.c(sep_char * 2, col.DIM) + header_text + col.c(sep_char * trail_len, col.DIM)
        )
        print(separator)
        _print_body(comment.body, term_width)
        if i < len(subset) - 1:
            print()
