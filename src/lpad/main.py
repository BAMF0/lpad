"""lpad - CLI entrypoint."""

import argparse
import sys


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
        print(f"Using cached bugs ({cache_info(package)}).", file=sys.stderr)

    if not bugs:
        print("No bugs found.")
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
        print("No bug selected.")
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
        print("Error: not inside a git repository.", file=sys.stderr)
        sys.exit(1)

    bug_id = parse_bug_number_from_branch(branch)
    if bug_id is None:
        print(
            f"Error: current branch '{branch}' does not look like an lp<N>-* branch.",
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
        print("Error: not inside a git repository.", file=sys.stderr)
        sys.exit(1)

    bug_id = parse_bug_number_from_branch(branch)
    if bug_id is None:
        print(
            f"Error: current branch '{branch}' does not look like an lp<N>-* branch.",
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
        print("No bug selected.")
        sys.exit(0)
    subscribe_to_bug(lp, selected.id)


def cmd_sync(args: argparse.Namespace) -> None:
    from lpad.auth import get_launchpad
    from lpad.bugs import get_package_bugs
    from lpad.cache import invalidate_cache
    from lpad.repo import detect_source_package

    package = detect_source_package()
    invalidate_cache(package)
    lp = get_launchpad()
    bugs = get_package_bugs(lp, package, force_refresh=True)
    print(f"Cache updated: {len(bugs)} bugs for {package}.")


def cmd_preview(args: argparse.Namespace) -> None:
    """Hidden subcommand called by fzf --preview to render a bug overview."""
    from lpad.bugs import LAUNCHPAD_BUG_URL, print_bug_summary
    from lpad.cache import CACHE_DIR, load_cache

    # fzf passes the first token of the selected line, e.g. "#2045432"
    raw = args.bug_token.lstrip("#")
    try:
        bug_id = int(raw)
    except ValueError:
        print(f"(could not parse bug ID from: {args.bug_token!r})")
        return

    # Scan all cache files — we don't need to detect the package since the
    # bug ID is unique across packages and we just want the cached data.
    if CACHE_DIR.exists():
        for cache_file in CACHE_DIR.glob("*.json"):
            package = cache_file.stem
            bugs = load_cache(package)
            if bugs:
                for bug in bugs:
                    if bug.id == bug_id:
                        print_bug_summary(bug)
                        return

    # Fallback: cache is cold or bug not found
    print(f"Bug #{bug_id}")
    print(f"  URL: {LAUNCHPAD_BUG_URL.format(bug_id=bug_id)}")
    print("  (run 'lpad sync' to populate the cache for full preview)")


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
    subparsers.required = True

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
        help="Refresh the bug cache for the current source package",
    )

    args = parser.parse_args()

    commands = {
        "list": cmd_list,
        "branch": cmd_branch,
        "report": cmd_report,
        "open": cmd_open,
        "status": cmd_status,
        "subscribe": cmd_subscribe,
        "sync": cmd_sync,
    }
    commands[args.command](args)
