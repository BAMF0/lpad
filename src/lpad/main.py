"""lpad - CLI entrypoint."""

import argparse
import sys
from datetime import UTC
from importlib.metadata import version as _pkg_version

import lpad.color as col

BRANCH_NAME_HINT = (
    "an lp<N>-*, <series>-lp<N>-*, <series>-sru-lp<N>-*, or merge-lp<N>-<series> branch"
)


def _resolve_status_filter(args: argparse.Namespace) -> list[str] | None:
    """Resolve the --status/--all flags into a status filter list (or None for all)."""
    if getattr(args, "all", False):
        return None
    raw = getattr(args, "status", None)
    if raw:
        return [s.strip() for s in raw.split(",") if s.strip()]
    from lpad.bugs import OPEN_STATUSES

    return OPEN_STATUSES


def _add_package_arg(parser: argparse.ArgumentParser) -> None:
    """Register -p/--package on *parser*.

    Allows operating on a specific source package without being inside its
    git checkout — useful for read-only browsing from anywhere.
    """
    parser.add_argument(
        "-p",
        "--package",
        type=str,
        default=None,
        help="Source package name (bypasses git-remote detection). "
        "Lets you read bug info for a package without being inside its checkout.",
    )


def _resolve_package(args: argparse.Namespace, interactive: bool = True) -> str:
    """Return the explicitly-passed package, or fall back to git detection.

    When *interactive* is False and neither -p nor git detection yields a
    package, returns an empty string (callers should treat this as "no
    package") instead of prompting.
    """
    pkg: str | None = getattr(args, "package", None)
    if pkg:
        return pkg
    from lpad.repo import detect_source_package

    return detect_source_package(interactive=interactive)


# ---------------------------------------------------------------------------
# Subcommand handlers
# ---------------------------------------------------------------------------


def cmd_list(args: argparse.Namespace) -> None:
    from lpad.bugs import fzf_select_bug, print_bug_summary
    from lpad.cache import load_cache

    package = _resolve_package(args)
    status_filter = _resolve_status_filter(args)

    bugs = load_cache(package, status_filter=status_filter)
    if bugs is None:
        from lpad.auth import get_launchpad
        from lpad.bugs import get_package_bugs

        lp = get_launchpad()
        bugs = get_package_bugs(lp, package, status=status_filter)
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
    from lpad.branch import create_branch
    from lpad.bugs import fzf_select_bug, get_bug_by_id, get_package_bugs
    from lpad.repo import parse_changelog_series

    package = _resolve_package(args)
    status_filter = _resolve_status_filter(args)

    if args.bug_id is not None:
        lp = get_launchpad()
        bug = get_bug_by_id(lp, args.bug_id)
        try:
            title = bug.title
        except Exception:
            title = "(unavailable)"
        from lpad.bugs import BugSummary

        selected: BugSummary | None = BugSummary(
            id=bug.id,
            title=title,
            status="(unknown)",
            importance="Undecided",
            assignee=None,
        )
    else:
        lp = get_launchpad()
        bugs = get_package_bugs(lp, package, status=status_filter)
        selected = fzf_select_bug(bugs)
        if selected is None:
            print(col.info("No bug selected."))
            sys.exit(0)

    assert selected is not None
    series: str | None = args.series
    kind = "merge" if args.merge else ("sru" if args.sru else "normal")

    if kind == "merge":
        if not series:
            print(
                col.error("Error: --merge requires --series to specify the target release."),
                file=sys.stderr,
            )
            sys.exit(1)
    else:
        if series is None:
            series = parse_changelog_series()
            if series:
                print(col.info(f"Detected series '{series}' from debian/changelog."))

    create_branch(selected.id, series=series, kind=kind)


def cmd_report(args: argparse.Namespace) -> None:
    from lpad.auth import get_launchpad
    from lpad.bugs import LAUNCHPAD_BUG_URL
    from lpad.drafts import create_draft, get_draft, list_drafts, remove_draft, update_draft
    from lpad.editor import open_editor
    from lpad.templates import resolve_template

    package = _resolve_package(args)

    # Resolve the seed content: resume a draft, or use a template, or empty.
    draft = None
    title: str | None = None
    if args.resume is not None:
        draft = get_draft(args.resume, package=package)
        if draft is None:
            print(
                col.error(f"Error: no draft with id '{args.resume}' for {package}."),
                file=sys.stderr,
            )
            sys.exit(1)
        seed = f"Title: {draft.title}\n\n{draft.description}"
        title = draft.title
    elif getattr(args, "resume_pick", False):
        drafts = list_drafts(package=package)
        if not drafts:
            print(col.info(f"No saved drafts for {package}."))
            sys.exit(0)
        import subprocess

        lines = [f"#{d.id}  {d.title}  ({d.package})" for d in drafts]
        result = subprocess.run(
            ["fzf", "--ansi", "--prompt=Select draft> ", "--height=60%", "--reverse"],
            input="\n".join(lines),
            capture_output=True,
            text=True,
        )
        if result.returncode != 0 or not result.stdout.strip():
            print(col.info("No draft selected."))
            sys.exit(0)
        raw = result.stdout.strip().split()[0]
        draft_id = raw.lstrip("#")
        draft = get_draft(draft_id, package=package)
        if draft is None:
            print(col.error(f"Error: draft '{draft_id}' not found."), file=sys.stderr)
            sys.exit(1)
        seed = f"Title: {draft.title}\n\n{draft.description}"
        title = draft.title
    else:
        seed = resolve_template(getattr(args, "template", None))
        title = getattr(args, "title", None) or ""

    if getattr(args, "no_editor", False):
        # Read from stdin: first line is title, rest is description.
        import sys as _sys

        content = _sys.stdin.read()
        if not content.strip():
            print(col.error("Error: empty input on stdin."), file=sys.stderr)
            sys.exit(1)
        lines = content.splitlines()
        if not title:
            title = lines[0].strip()
            description = "\n".join(lines[1:]).strip()
        else:
            description = content.strip()
    else:
        content = open_editor(seed)
        if content is None:
            print(col.info("Aborted (empty content)."))
            sys.exit(0)
        # Parse "Title: <...>" from the first line if present.
        lines = content.splitlines()
        if lines and lines[0].startswith("Title: "):
            title = lines[0][len("Title: ") :].strip()
            description = "\n".join(lines[2:]).strip() if len(lines) > 2 else ""
        else:
            if not title:
                title = ""
            description = content.strip()

    if not title:
        title = input(col.prompt("Title: ")).strip()
        if not title:
            print(col.error("Error: title cannot be empty."), file=sys.stderr)
            sys.exit(1)
    if not description:
        print(col.error("Error: description cannot be empty."), file=sys.stderr)
        sys.exit(1)

    # Offer to save as draft before submitting.
    if not draft and not _confirm("Submit now? [Y/n] ", default=True):
        draft = create_draft(package, title, description)
        print(
            col.success(
                f"Saved as draft #{draft.id} for {package}. "
                f"Resume with: lpad report --resume={draft.id}"
            )
        )
        return

    # If we have an existing draft, update it before submitting.
    if draft:
        draft.title = title
        draft.description = description
        update_draft(draft)

    lp = get_launchpad()
    ubuntu = lp.distributions["ubuntu"]
    spkg = ubuntu.getSourcePackage(name=package)
    try:
        bug = lp.bugs.createBug(
            target=spkg,
            title=title,
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

    # Post-submit: offer to delete the source draft (default: keep).
    if draft and _confirm(f"Delete draft #{draft.id}? [y/N] ", default=False):
        remove_draft(draft.id, package=package)
        print(col.info(f"Draft #{draft.id} deleted."))


def cmd_open(args: argparse.Namespace) -> None:
    from lpad.bugs import open_bug_in_browser

    if args.bug_id is not None:
        open_bug_in_browser(args.bug_id)
        return

    from lpad.repo import get_current_branch, parse_bug_number_from_branch

    branch = get_current_branch()
    if not branch:
        print(col.error("Error: not inside a git repository."), file=sys.stderr)
        sys.exit(1)

    bug_id = parse_bug_number_from_branch(branch)
    if bug_id is None:
        print(
            col.error(f"Error: current branch '{branch}' does not look like {BRANCH_NAME_HINT}."),
            file=sys.stderr,
        )
        sys.exit(1)

    open_bug_in_browser(bug_id)


def cmd_status(args: argparse.Namespace) -> None:
    from lpad.auth import get_launchpad
    from lpad.bugs import print_bug_status

    if args.bug_id is not None:
        bug_id = args.bug_id
    else:
        from lpad.repo import get_current_branch, parse_bug_number_from_branch

        branch = get_current_branch()
        if not branch:
            print(col.error("Error: not inside a git repository."), file=sys.stderr)
            sys.exit(1)

        bug_id = parse_bug_number_from_branch(branch)
        if bug_id is None:
            print(
                col.error(
                    f"Error: current branch '{branch}' does not look like {BRANCH_NAME_HINT}.\n"
                    "Usage: lpad status [bug_id]"
                ),
                file=sys.stderr,
            )
            sys.exit(1)

    package = _resolve_package(args, interactive=False) or None
    lp = get_launchpad()
    print_bug_status(lp, bug_id, package, verbose=args.verbose)


def cmd_subscribe(args: argparse.Namespace) -> None:
    from lpad.auth import get_launchpad
    from lpad.bugs import fzf_select_bug, get_package_bugs, subscribe_to_bug

    package = _resolve_package(args)
    status_filter = _resolve_status_filter(args)

    if args.bug_id is not None:
        lp = get_launchpad()
        subscribe_to_bug(lp, args.bug_id)
        return

    lp = get_launchpad()
    bugs = get_package_bugs(lp, package, status=status_filter)
    selected = fzf_select_bug(bugs)
    if selected is None:
        print(col.info("No bug selected."))
        sys.exit(0)
    subscribe_to_bug(lp, selected.id)


def cmd_sync(args: argparse.Namespace) -> None:
    from lpad.auth import get_launchpad
    from lpad.bugs import get_bug_comments, get_package_bugs
    from lpad.cache import invalidate_cache, invalidate_comment_cache
    from lpad.repo import get_current_branch, parse_bug_number_from_branch

    package = _resolve_package(args)
    invalidate_cache(package)
    lp = get_launchpad()
    bugs = get_package_bugs(lp, package, force_refresh=True)
    print(col.success(f"Cache updated: {len(bugs)} bugs for {package}."))

    branch = get_current_branch()
    bug_id = parse_bug_number_from_branch(branch) if branch else None
    if bug_id is not None:
        invalidate_comment_cache(bug_id)
        comments = get_bug_comments(lp, bug_id, force_refresh=True)
        print(col.success(f"Comment cache updated: {len(comments)} comments for bug #{bug_id}."))
    else:
        print(col.info(f"Skipping comment cache refresh (not on {BRANCH_NAME_HINT})."))


def cmd_comments(args: argparse.Namespace) -> None:
    from lpad.bugs import get_bug_comments, print_comments
    from lpad.repo import get_current_branch, parse_bug_number_from_branch

    if args.bug_id is not None:
        bug_id = args.bug_id
    else:
        branch = get_current_branch()
        bug_id = parse_bug_number_from_branch(branch) if branch else None

    if bug_id is None:
        print(
            col.error(
                f"Error: no bug ID given and current branch is not {BRANCH_NAME_HINT}.\n"
                "Usage: lpad comments [bug_id]"
            ),
            file=sys.stderr,
        )
        sys.exit(1)

    if args.first is not None and args.last is not None:
        print(
            col.error("Error: --first/--head and --last/--tail are mutually exclusive."),
            file=sys.stderr,
        )
        sys.exit(1)

    from lpad.cache import comment_cache_info, load_comment_cache

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
    from lpad.bugs import LAUNCHPAD_BUG_URL, _strip_ansi, print_bug_summary
    from lpad.cache import CACHE_DIR, load_cache

    raw = _strip_ansi(args.bug_token).lstrip("#")
    try:
        bug_id = int(raw)
    except ValueError:
        print(col.error(f"(could not parse bug ID from: {args.bug_token!r})"))
        return

    if CACHE_DIR.exists():
        for cache_file in CACHE_DIR.glob("*.json"):
            bugs = load_cache(cache_file.stem, ignore_status_filter=True)
            if bugs:
                for bug in bugs:
                    if bug.id == bug_id:
                        print_bug_summary(bug)
                        return

    print(col.bug_id(f"Bug #{bug_id}"))
    print(f"  {col.label('URL:')} {col.url(LAUNCHPAD_BUG_URL.format(bug_id=bug_id))}")
    print(col.info("  (run 'lpad sync' to populate the cache for full preview)"))


# --- info subcommand ---


def cmd_info(args: argparse.Namespace) -> None:
    from lpad.bugs import print_package_dashboard
    from lpad.cache import cache_info, load_cache

    package = args.package
    status_filter = _resolve_status_filter(args)

    bugs = load_cache(package, status_filter=status_filter)
    info_str = cache_info(package)

    if bugs is None:
        if args.refresh:
            from lpad.auth import get_launchpad
            from lpad.bugs import get_package_bugs

            lp = get_launchpad()
            bugs = get_package_bugs(lp, package, force_refresh=True, status=status_filter)
            info_str = cache_info(package)
        else:
            print(
                col.info(
                    f"No fresh cache for {package}. "
                    f"Run 'lpad info {package} --refresh' or 'lpad sync -p {package}' first."
                ),
                file=sys.stderr,
            )
            sys.exit(1)

    print_package_dashboard(package, bugs, cache_info_str=info_str)


# --- cache subcommand ---


def cmd_cache(args: argparse.Namespace) -> None:
    from lpad.cache import (
        CACHE_DIR,
        cache_info,
        invalidate_cache,
        invalidate_comment_cache,
    )

    action = args.cache_action
    if action == "list":
        if not CACHE_DIR.exists():
            print(col.info("No caches found."))
            return
        files = sorted(CACHE_DIR.glob("*.json"))
        if not files:
            print(col.info("No caches found."))
            return
        for f in files:
            info = cache_info(f.stem) or "(unreadable)"
            print(f"  {f.stem:<30} {info}")
        comment_dir = CACHE_DIR / "comments"
        if comment_dir.exists():
            cf = sorted(comment_dir.glob("*.json"))
            if cf:
                print(col.info(f"  ({len(cf)} comment cache file(s))"))
    elif action == "info":
        pkg = args.package
        cache_info_str: str | None = cache_info(pkg)
        if cache_info_str:
            print(f"  {pkg}: {cache_info_str}")
        else:
            print(col.info(f"No cache for {pkg}."))
    elif action == "clear":
        pkg = args.package
        if pkg:
            invalidate_cache(pkg)
            print(col.success(f"Cleared bug cache for {pkg}."))
        else:
            if CACHE_DIR.exists():
                for f in CACHE_DIR.glob("*.json"):
                    f.unlink()
                print(col.success("Cleared all bug caches."))
            else:
                print(col.info("No caches to clear."))
    elif action == "clear-comments":
        bug_id = args.bug_id
        if bug_id:
            invalidate_comment_cache(bug_id)
            print(col.success(f"Cleared comment cache for bug #{bug_id}."))
        else:
            comment_dir = CACHE_DIR / "comments"
            if comment_dir.exists():
                for f in comment_dir.glob("*.json"):
                    f.unlink()
                print(col.success("Cleared all comment caches."))
            else:
                print(col.info("No comment caches to clear."))


# --- template subcommand ---


def cmd_template(args: argparse.Namespace) -> None:
    from lpad.editor import open_editor
    from lpad.templates import (
        get_template,
        list_templates,
        refresh_template,
        remove_user_template,
        save_user_template,
    )

    action = args.template_action
    if action == "list":
        templates = list_templates()
        if not templates:
            print(col.info("No templates available."))
            return
        for t in templates:
            print(f"  {t.name:<20} ({t.source})  {t.length} bytes")
    elif action == "show":
        content = get_template(args.name)
        if content is None:
            print(col.error(f"Error: unknown template '{args.name}'."), file=sys.stderr)
            sys.exit(1)
        print(content, end="")
    elif action == "edit":
        seed = get_template(args.name)
        if seed is None:
            print(col.error(f"Error: unknown template '{args.name}'."), file=sys.stderr)
            sys.exit(1)
        edited = open_editor(seed)
        if edited is None:
            print(col.info("Aborted (empty content)."))
            return
        path = save_user_template(args.name, edited)
        print(col.success(f"Saved user template '{args.name}' → {path}"))
    elif action == "refresh":
        refresh_template(args.name)
    elif action == "remove":
        if remove_user_template(args.name):
            print(col.success(f"Removed user override for '{args.name}'."))
        else:
            print(col.error(f"Error: no user override for '{args.name}'."), file=sys.stderr)
            sys.exit(1)


# --- draft subcommand ---


def cmd_draft(args: argparse.Namespace) -> None:
    from datetime import datetime

    from lpad.drafts import get_draft, list_drafts, prune_drafts, remove_draft

    action = args.draft_action
    if action == "list":
        pkg_filter = getattr(args, "package", None)
        drafts = list_drafts(package=pkg_filter)
        if not drafts:
            print(col.info("No drafts found."))
            return
        for d in drafts:
            dt = datetime.fromtimestamp(d.created_at, tz=UTC)
            date_str = dt.strftime("%Y-%m-%d %H:%M")
            first_line = d.title.splitlines()[0] if d.title else "(no title)"
            print(f"  #{d.id}  {date_str}  {d.package:<20}  {first_line}")
    elif action == "show":
        draft = get_draft(args.id)
        if draft is None:
            print(col.error(f"Error: no draft with id '{args.id}'."), file=sys.stderr)
            sys.exit(1)
        print(f"Title: {draft.title}")
        print()
        print(draft.description, end="")
        if not draft.description.endswith("\n"):
            print()
    elif action == "remove":
        if not args.force and not _confirm(f"Delete draft #{args.id}? [y/N] ", default=False):
            print(col.info("Not deleted."))
            return
        if remove_draft(args.id):
            print(col.success(f"Deleted draft #{args.id}."))
        else:
            print(col.error(f"Error: no draft with id '{args.id}'."), file=sys.stderr)
            sys.exit(1)
    elif action == "prune":
        removed = prune_drafts(older_than_days=args.days, dry_run=args.dry_run)
        if args.dry_run:
            if removed:
                print(col.info(f"Would remove {len(removed)} draft(s):"))
                for p in removed:
                    print(f"  {p}")
            else:
                print(col.info("No drafts to prune."))
        else:
            print(col.success(f"Pruned {len(removed)} draft(s)."))


# --- completion subcommand ---


def cmd_completion(args: argparse.Namespace) -> None:
    try:
        import shtab
    except ImportError:
        print(
            col.error("Error: shtab is not installed. Install with: pip install shtab"),
            file=sys.stderr,
        )
        sys.exit(1)
    supported = {"bash", "zsh", "tcsh"}
    shell = args.shell
    if shell not in supported:
        print(
            col.error(
                f"Error: unsupported shell '{shell}'. Supported: {', '.join(sorted(supported))}"
            ),
            file=sys.stderr,
        )
        sys.exit(1)
    print(shtab.complete(_build_parser(), shell=shell))


# --- helpers ---


def _confirm(prompt: str, default: bool) -> bool:
    """Ask a yes/no question. Returns *default* on empty input."""
    try:
        answer = input(col.prompt(prompt)).strip().lower()
    except (EOFError, KeyboardInterrupt):
        return default
    if not answer:
        return default
    return answer in ("y", "yes")


# ---------------------------------------------------------------------------
# Argparse construction
# ---------------------------------------------------------------------------


def _add_status_filter(parser: argparse.ArgumentParser) -> None:
    """Add --status and --all flags to *parser*."""
    group = parser.add_mutually_exclusive_group()
    group.add_argument(
        "--status",
        type=str,
        default=None,
        help="Comma-separated list of Launchpad statuses to filter by "
        "(e.g. 'New,In Progress'). Default: open statuses only.",
    )
    group.add_argument(
        "--all",
        action="store_true",
        default=False,
        help="Include bugs of all statuses (overrides the default open-only filter).",
    )


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="lpad",
        description="A focused CLI tool for working with Launchpad bugs.",
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"lpad {_pkg_version('lpad')}",
    )
    subparsers = parser.add_subparsers(dest="command", metavar="<command>")
    subparsers.required = False

    # list
    list_parser = subparsers.add_parser(
        "list",
        help="Browse bugs for the current source package via fzf",
    )
    _add_package_arg(list_parser)
    _add_status_filter(list_parser)

    # branch
    branch_parser = subparsers.add_parser(
        "branch",
        help="Pick a bug and create a git branch",
        description=(
            "Pick a bug and create a git branch. Branch naming:\n"
            "  normal: lp<N>-<desc> or <series>-lp<N>-<desc>\n"
            "  --sru:  <series>-sru-lp<N>-<desc>\n"
            "  --merge: merge-lp<N>-<series>  (no description, --series required)\n"
            "--sru and --merge are mutually exclusive."
        ),
    )
    branch_parser.add_argument(
        "bug_id",
        nargs="?",
        type=int,
        default=None,
        help="Bug ID to branch from (skips the fzf picker if given)",
    )
    _add_package_arg(branch_parser)
    branch_parser.add_argument(
        "--series",
        "-s",
        type=str,
        default=None,
        help="Target Ubuntu series for the branch (e.g. noble). "
        "If omitted, lpad auto-detects from debian/changelog "
        "(required with --merge).",
    )
    branch_kind_group = branch_parser.add_mutually_exclusive_group()
    branch_kind_group.add_argument(
        "--sru",
        action="store_true",
        default=False,
        help="Create an SRU branch: <series>-sru-lp<N>-<desc>.",
    )
    branch_kind_group.add_argument(
        "--merge",
        action="store_true",
        default=False,
        help="Create a merge branch: merge-lp<N>-<series>. Requires --series.",
    )
    _add_status_filter(branch_parser)

    # report
    report_parser = subparsers.add_parser(
        "report",
        help="File a new bug against the current source package",
        description=(
            "File a new bug against the current source package. "
            "Opens $EDITOR with an optional template. "
            "Drafts can be saved and resumed later."
        ),
    )
    _add_package_arg(report_parser)
    report_parser.add_argument(
        "--template",
        type=str,
        default=None,
        help="Seed the editor with a template: a built-in name "
        "(ubuntu, sru, regression) or a file path.",
    )
    report_resume_group = report_parser.add_mutually_exclusive_group()
    report_resume_group.add_argument(
        "--resume",
        type=str,
        default=None,
        help="Resume a saved draft by its short ID.",
    )
    report_resume_group.add_argument(
        "--resume-pick",
        action="store_true",
        default=False,
        dest="resume_pick",
        help="Pick a saved draft via fzf to resume.",
    )
    report_resume_group.add_argument(
        "--no-editor",
        action="store_true",
        default=False,
        help="Read title and description from stdin instead of opening $EDITOR.",
    )
    report_parser.add_argument(
        "--title",
        type=str,
        default=None,
        help="Pre-set the bug title (skips the title prompt).",
    )

    # open
    open_parser = subparsers.add_parser(
        "open",
        help="Open a bug in the browser (current branch's bug, or a given bug ID)",
    )
    open_parser.add_argument(
        "bug_id",
        nargs="?",
        type=int,
        default=None,
        help="Bug ID to open (defaults to current branch's bug)",
    )

    # status
    status_parser = subparsers.add_parser(
        "status",
        help="Print a compact status summary for a bug",
    )
    status_parser.add_argument(
        "bug_id",
        nargs="?",
        type=int,
        default=None,
        help="Bug ID to show status for (defaults to current branch's bug)",
    )
    _add_package_arg(status_parser)
    status_parser.add_argument(
        "--verbose",
        "-V",
        action="store_true",
        default=False,
        help="Also print the bug description and heat",
    )

    # subscribe
    subscribe_parser = subparsers.add_parser(
        "subscribe",
        help="Subscribe yourself to a bug",
    )
    subscribe_parser.add_argument(
        "bug_id",
        nargs="?",
        type=int,
        default=None,
        help="Bug ID to subscribe to (skips the fzf picker if given)",
    )
    _add_package_arg(subscribe_parser)
    _add_status_filter(subscribe_parser)

    # sync
    sync_parser = subparsers.add_parser(
        "sync",
        help=f"Refresh the bug cache (and comment cache if on {BRANCH_NAME_HINT})",
    )
    _add_package_arg(sync_parser)

    # comments
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
        "--first",
        "--head",
        dest="first",
        metavar="N",
        type=int,
        default=None,
        help="Show only the first N comments",
    )
    comments_group.add_argument(
        "--last",
        "--tail",
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

    # cache
    cache_parser = subparsers.add_parser(
        "cache",
        help="Inspect and manage the local bug/comment caches",
    )
    cache_sub = cache_parser.add_subparsers(dest="cache_action", metavar="<action>")
    cache_sub.required = True
    cache_sub.add_parser("list", help="List all cached packages")
    cache_info_p = cache_sub.add_parser("info", help="Show cache info for a package")
    cache_info_p.add_argument("package", type=str, help="Source package name")
    cache_clear_p = cache_sub.add_parser("clear", help="Clear bug cache")
    cache_clear_p.add_argument(
        "package", nargs="?", type=str, help="Source package (clears all if omitted)"
    )
    cache_clear_comments_p = cache_sub.add_parser("clear-comments", help="Clear comment cache")
    cache_clear_comments_p.add_argument(
        "bug_id", nargs="?", type=int, help="Bug ID (clears all if omitted)"
    )

    # template
    template_parser = subparsers.add_parser(
        "template",
        help="Manage bug report templates",
    )
    template_sub = template_parser.add_subparsers(dest="template_action", metavar="<action>")
    template_sub.required = True
    template_sub.add_parser("list", help="List available templates")
    template_show_p = template_sub.add_parser("show", help="Print a template")
    template_show_p.add_argument("name", type=str, help="Template name")
    template_edit_p = template_sub.add_parser(
        "edit", help="Edit a template in $EDITOR (saves a user override)"
    )
    template_edit_p.add_argument("name", type=str, help="Template name")
    template_refresh_p = template_sub.add_parser(
        "refresh", help="Refresh a template from its canonical web source"
    )
    template_refresh_p.add_argument("name", type=str, help="Template name (e.g. sru)")
    template_remove_p = template_sub.add_parser(
        "remove", help="Remove a user override, reverting to the built-in"
    )
    template_remove_p.add_argument("name", type=str, help="Template name")

    # draft
    draft_parser = subparsers.add_parser(
        "draft",
        help="Manage saved bug report drafts",
    )
    draft_sub = draft_parser.add_subparsers(dest="draft_action", metavar="<action>")
    draft_sub.required = True
    draft_list_p = draft_sub.add_parser("list", help="List all drafts")
    _add_package_arg(draft_list_p)
    draft_show_p = draft_sub.add_parser("show", help="Print a draft")
    draft_show_p.add_argument("id", type=str, help="Draft ID")
    draft_remove_p = draft_sub.add_parser("remove", help="Delete a draft")
    draft_remove_p.add_argument("id", type=str, help="Draft ID")
    draft_remove_p.add_argument(
        "--force", action="store_true", default=False, help="Skip confirmation"
    )
    draft_prune_p = draft_sub.add_parser("prune", help="Remove drafts older than N days")
    draft_prune_p.add_argument(
        "--days", type=int, default=30, help="Age threshold in days (default: 30)"
    )
    draft_prune_p.add_argument(
        "--dry-run", action="store_true", default=False, help="Preview without deleting"
    )

    # info
    info_parser = subparsers.add_parser(
        "info",
        help="Print a read-only dashboard for a source package (from cache)",
        description=(
            "Print a read-only overview of bugs for a source package: "
            "counts by status/importance, top assignees, and cache age. "
            "Reads from the local cache; use --refresh to fetch first.\n\n"
            "Works outside a git checkout — pass the package name explicitly."
        ),
    )
    info_parser.add_argument(
        "package",
        type=str,
        help="Source package name (e.g. curl)",
    )
    info_parser.add_argument(
        "--refresh",
        action="store_true",
        default=False,
        help="Fetch from Launchpad before printing (updates the cache).",
    )
    _add_status_filter(info_parser)

    # completion
    completion_parser = subparsers.add_parser(
        "completion",
        help="Print a shell completion script",
    )
    completion_parser.add_argument(
        "shell",
        choices=["bash", "zsh", "tcsh"],
        help="Target shell",
    )

    return parser


def main() -> None:
    if len(sys.argv) >= 2 and sys.argv[1] == "_preview":
        bug_token = sys.argv[2] if len(sys.argv) > 2 else ""

        class _PreviewArgs:
            pass

        a = _PreviewArgs()
        a.bug_token = bug_token  # type: ignore[attr-defined]
        cmd_preview(a)  # type: ignore[arg-type]
        return

    parser = _build_parser()
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
        "cache": cmd_cache,
        "template": cmd_template,
        "draft": cmd_draft,
        "info": cmd_info,
        "completion": cmd_completion,
    }

    try:
        commands[args.command](args)
    except KeyboardInterrupt:
        print(col.info("\nInterrupted."), file=sys.stderr)
        sys.exit(130)


if __name__ == "__main__":
    main()
