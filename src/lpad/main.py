"""lpad - CLI entrypoint."""

import argparse
import sys

import lpad.color as col


def cmd_list(args: argparse.Namespace) -> None:
    from lpad.bugs import fzf_select_bug, print_bug_summary
    from lpad.cache import load_cache
    from lpad.repo import detect_source_package

    package = detect_source_package()

    # Check cache before authenticating — warm cache needs zero HTTP calls.
    bugs = load_cache(package)
    if bugs is None:
        from lpad.auth import get_launchpad
        from lpad.bugs import get_package_bugs
        lp = get_launchpad()
        bugs = get_package_bugs(lp, package)
    else:
        from lpad.cache import cache_info
        print(col.info(f"Using cached bugs ({cache_info(package)})."), file=sys.stderr)

    if not bugs:
        print(col.info("No bugs found."))
        return

    selected = fzf_select_bug(bugs)
    if selected is None:
        return
    print()
    print_bug_summary(selected)


def cmd_branch(args: argparse.Namespace) -> None:
    from lpad.auth import get_launchpad
    from lpad.bugs import get_package_bugs, fzf_select_bug
    from lpad.branch import create_branch
    from lpad.repo import detect_source_package

    package = detect_source_package()
    lp = get_launchpad()
    bugs = get_package_bugs(lp, package)
    selected = fzf_select_bug(bugs)
    if selected is None:
        print(col.info("No bug selected."))
        sys.exit(0)
    create_branch(selected.id)


def cmd_report(args: argparse.Namespace) -> None:
    from lpad.auth import get_launchpad
    from lpad.bugs import report_bug
    from lpad.repo import detect_source_package

    package = detect_source_package()
    lp = get_launchpad()
    report_bug(lp, package)


def cmd_open(args: argparse.Namespace) -> None:
    from lpad.bugs import open_bug_in_browser
    from lpad.repo import get_current_branch, parse_bug_number_from_branch

    branch = get_current_branch()
    if not branch:
        print(col.error("Error: not inside a git repository."), file=sys.stderr)
        sys.exit(1)

    bug_id = parse_bug_number_from_branch(branch)
    if bug_id is None:
        print(
            col.error(
                f"Error: current branch '{branch}' does not look like an lp<N>-* branch."
            ),
            file=sys.stderr,
        )
        sys.exit(1)

    open_bug_in_browser(bug_id)


def cmd_status(args: argparse.Namespace) -> None:
    from lpad.auth import get_launchpad
    from lpad.bugs import print_bug_status
    from lpad.repo import (
        detect_source_package,
        get_current_branch,
        parse_bug_number_from_branch,
    )

    branch = get_current_branch()
    if not branch:
        print(col.error("Error: not inside a git repository."), file=sys.stderr)
        sys.exit(1)

    bug_id = parse_bug_number_from_branch(branch)
    if bug_id is None:
        print(
            col.error(
                f"Error: current branch '{branch}' does not look like an lp<N>-* branch."
            ),
            file=sys.stderr,
        )
        sys.exit(1)

    package = detect_source_package()
    lp = get_launchpad()
    print_bug_status(lp, bug_id, package, verbose=args.verbose)


def cmd_subscribe(args: argparse.Namespace) -> None:
    from lpad.auth import get_launchpad
    from lpad.bugs import get_package_bugs, fzf_select_bug, subscribe_to_bug
    from lpad.repo import detect_source_package

    package = detect_source_package()
    lp = get_launchpad()
    bugs = get_package_bugs(lp, package)
    selected = fzf_select_bug(bugs)
    if selected is None:
        print(col.info("No bug selected."))
        sys.exit(0)
    subscribe_to_bug(lp, selected.id)


def cmd_sync(args: argparse.Namespace) -> None:
    from lpad.auth import get_launchpad
    from lpad.bugs import get_package_bugs, get_bug_comments
    from lpad.cache import invalidate_cache, invalidate_comment_cache
    from lpad.repo import detect_source_package, get_current_branch, parse_bug_number_from_branch

    package = detect_source_package()
    invalidate_cache(package)
    lp = get_launchpad()
    bugs = get_package_bugs(lp, package, force_refresh=True)
    print(col.success(f"Cache updated: {len(bugs)} bugs for {package}."))

    # Refresh comment cache only for the current branch's bug, if on one.
    branch = get_current_branch()
    bug_id = parse_bug_number_from_branch(branch) if branch else None
    if bug_id is not None:
        invalidate_comment_cache(bug_id)
        comments = get_bug_comments(lp, bug_id, force_refresh=True)
        print(col.success(
            f"Comment cache updated: {len(comments)} comments for bug #{bug_id}."
        ))
    else:
        print(col.info(
            "Skipping comment cache refresh (not on an lp<N>-* branch)."
        ))


def cmd_comments(args: argparse.Namespace) -> None:
    from lpad.bugs import get_bug_comments, print_comments
    from lpad.repo import get_current_branch, parse_bug_number_from_branch

    # Resolve bug ID: explicit arg takes priority, then branch name
    if args.bug_id is not None:
        bug_id = args.bug_id
    else:
        branch = get_current_branch()
        if branch:
            bug_id = parse_bug_number_from_branch(branch)
        else:
            bug_id = None

    if bug_id is None:
        print(
            col.error(
                "Error: no bug ID given and current branch is not an lp<N>-* branch.\n"
                "Usage: lpad comments [bug_id]"
            ),
            file=sys.stderr,
        )
        sys.exit(1)

    # Validate mutual exclusivity of --first/--last (argparse handles it, but
    # --head/--tail are stored in the same dest so check here)
    if args.first is not None and args.last is not None:
        print(
            col.error("Error: --first/--head and --last/--tail are mutually exclusive."),
            file=sys.stderr,
        )
        sys.exit(1)

    from lpad.cache import load_comment_cache, comment_cache_info
    comments = load_comment_cache(bug_id)
    if comments is None:
        from lpad.auth import get_launchpad
        lp = get_launchpad()
        comments = get_bug_comments(lp, bug_id)
    else:
        print(
            col.info(f"Using cached comments ({comment_cache_info(bug_id)})."),
            file=sys.stderr,
        )

    print_comments(
        comments,
        first=args.first,
        last=args.last,
        reverse=args.reverse,
    )


def cmd_preview(args: argparse.Namespace) -> None:
    """Hidden subcommand called by fzf --preview to render a bug overview."""
    from lpad.bugs import LAUNCHPAD_BUG_URL, print_bug_summary
    from lpad.cache import CACHE_DIR, load_cache

    # fzf passes the first token of the selected line, strip ANSI then '#'
    import re
    raw = re.sub(r"\033\[[0-9;]*m", "", args.bug_token).lstrip("#")
    try:
        bug_id = int(raw)
    except ValueError:
        print(col.error(f"(could not parse bug ID from: {args.bug_token!r})"))
        return

    # Scan all cache files — bug IDs are unique across packages
    if CACHE_DIR.exists():
        for cache_file in CACHE_DIR.glob("*.json"):
            bugs = load_cache(cache_file.stem)
            if bugs:
                for bug in bugs:
                    if bug.id == bug_id:
                        print_bug_summary(bug)
                        return

    # Fallback: cache cold or bug not found
    print(col.bug_id(f"Bug #{bug_id}"))
    print(f"  {col.label('URL:')} {col.url(LAUNCHPAD_BUG_URL.format(bug_id=bug_id))}")
    print(col.info("  (run 'lpad sync' to populate the cache for full preview)"))


def main() -> None:
    # Handle the hidden _preview subcommand before argparse sees it,
    # so it never appears in --help output.
    if len(sys.argv) >= 2 and sys.argv[1] == "_preview":
        bug_token = sys.argv[2] if len(sys.argv) > 2 else ""

        class _PreviewArgs:
            pass

        a = _PreviewArgs()
        a.bug_token = bug_token  # type: ignore[attr-defined]
        cmd_preview(a)  # type: ignore[arg-type]
        return

    parser = argparse.ArgumentParser(
        prog="lpad",
        description="A focused CLI tool for working with Launchpad bugs.",
    )
    subparsers = parser.add_subparsers(dest="command", metavar="<command>")
    subparsers.required = False

    subparsers.add_parser(
        "list",
        help="Browse all bugs for the current source package via fzf; shows status on selection",
    )
    subparsers.add_parser(
        "branch",
        help="Pick a bug with fzf and create a git branch lp<N>-<description>",
    )
    subparsers.add_parser(
        "report",
        help="File a new bug against the current source package",
    )
    subparsers.add_parser(
        "open",
        help="Open the current branch's bug in the browser",
    )
    status_parser = subparsers.add_parser(
        "status",
        help="Print a compact status summary for the current branch's bug",
    )
    status_parser.add_argument(
        "--verbose", "-V",
        action="store_true",
        default=False,
        help="Also print the bug description and heat",
    )
    subparsers.add_parser(
        "subscribe",
        help="Subscribe yourself to a bug picked via fzf",
    )
    subparsers.add_parser(
        "sync",
        help="Refresh the bug cache for the current source package (and comment cache if on an lp<N>-* branch)",
    )

    comments_parser = subparsers.add_parser(
        "comments",
        help="Show comments for the current branch's bug (or a given bug ID)",
    )
    comments_parser.add_argument(
        "bug_id",
        nargs="?",
        type=int,
        default=None,
        help="Bug ID to show comments for (defaults to current branch's bug)",
    )
    comments_group = comments_parser.add_mutually_exclusive_group()
    comments_group.add_argument(
        "--first", "--head",
        dest="first",
        metavar="N",
        type=int,
        default=None,
        help="Show only the first N comments",
    )
    comments_group.add_argument(
        "--last", "--tail",
        dest="last",
        metavar="N",
        type=int,
        default=None,
        help="Show only the last N comments",
    )
    comments_parser.add_argument(
        "--reverse",
        action="store_true",
        default=False,
        help="Display comments in reverse order (newest first)",
    )

    args = parser.parse_args()
    if args.command is None:
        parser.print_help()
        sys.exit(0)

    commands = {
        "list": cmd_list,
        "branch": cmd_branch,
        "report": cmd_report,
        "open": cmd_open,
        "status": cmd_status,
        "subscribe": cmd_subscribe,
        "sync": cmd_sync,
        "comments": cmd_comments,
    }
    commands[args.command](args)
