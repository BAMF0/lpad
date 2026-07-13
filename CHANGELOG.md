# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- **`lpad info <package>`**: read-only package dashboard — total bug count,
  breakdowns by status and importance, top assignees, and remote-watch tally.
  Reads from the local cache; `--refresh` fetches first. Accepts
  `--status=<csv>` / `--all`.
- **`-p` / `--package` flag** on `list`, `branch`, `report`, `status`,
  `subscribe`, `sync`, and `draft list`: bypasses git-remote source-package
  detection so bug data can be browsed from outside a checkout.
- **Optional `bug_id` positional** on `lpad open` and `lpad status`: look up
  a bug directly without a git repo or branch context. Omitting it preserves
  the previous branch-parsing behaviour.

### Changed

- `lpad status` without a resolvable package now prints bug-level status only
  (no Ubuntu task matching) instead of erroring; `print_bug_status` accepts
  `package_name: str | None`.
- `detect_source_package()` gained an `interactive` parameter; the
  non-interactive variant returns an empty string rather than prompting.
- `draft list` accepts `-p <pkg>` to filter drafts by source package.
- fzf preview window reduced from 50% to 40% of the terminal width.
- `load_cache()` accepts `ignore_status_filter`; the hidden fzf preview uses
  it to look up bugs by ID regardless of the status filter that populated
  the cache.

### Fixed

- `lpad list` fzf line no longer loses the bug title on narrow terminals:
  fixed columns are tightened, long titles truncate with an ellipsis, and
  the assignee is dropped when horizontal space is scarce.

## [0.1.0] - 2026-07-06

Initial release.

### Added

- **Bug browsing**: `lpad list` opens an fzf picker with a live preview panel
  for all bugs on the current source package. Defaults to open-statuses only;
  use `--all` or `--status=New,In Progress` to override.
- **Branch creation**: `lpad branch` picks a bug via fzf (or accepts a
  positional `<bug_id>`) and creates a git branch. Three naming modes:
  - Normal: `lp<N>-<desc>` or `<series>-lp<N>-<desc>`
  - `--sru`: `<series>-sru-lp<N>-<desc>`
  - `--merge`: `merge-lp<N>-<series>` (requires `--series`)
- **Bug reporting**: `lpad report` opens `$EDITOR` on a temp file seeded with
  an optional template, then submits to Launchpad. Supports `--template=<name>`
  (built-in: `ubuntu`, `sru`, `regression`) or `--template=<path>` for custom
  files. `--no-editor` reads from stdin for scripting. `--title` pre-sets the
  title.
- **Draft workflow**: Reports can be saved as drafts and resumed later.
  `lpad report --resume=<id>` opens a specific draft; `--resume-pick` selects
  via fzf. After submission, a `[y/N]` prompt offers to delete the source draft
  (default: keep).
- **Template management**: `lpad template` subcommand group — `list`, `show`,
  `edit` (opens `$EDITOR`, saves a user override), `refresh` (fetches the
  latest SRU template from ubuntu.com), `remove` (reverts to built-in).
- **Draft management**: `lpad draft` subcommand group — `list`, `show`,
  `remove` (with `--force`), `prune` (removes drafts older than N days, with
  `--dry-run`).
- **Bug status**: `lpad status` prints a live summary for the current branch's
  bug, including remote watches. `--verbose` adds description and heat.
- **Comments**: `lpad comments [bug_id]` shows comments for a bug (current
  branch's or by ID). Supports `--first N` / `--last N` / `--reverse`.
- **Subscribe**: `lpad subscribe [bug_id]` subscribes the authenticated user
  to a bug.
- **Cache sync**: `lpad sync` refreshes the bug cache and, if on a bug branch,
  the comment cache for that bug.
- **Open in browser**: `lpad open` opens the current branch's bug in the
  default browser.
- **Cache management**: `lpad cache` subcommand group — `list`, `info
  <package>`, `clear [package]`, `clear-comments [bug_id]`.
- **Shell completion**: `lpad completion {bash,zsh,tcsh}` prints a completion
  script via `shtab`.
- **`--version`** flag on the top-level parser.
- Local JSON cache (`~/.cache/lpad/`) with 24-hour TTL, overridable via
  `LPAD_CACHE_TTL`. Cache files record the status filter used; switching
  filters triggers a refetch.
- OAuth authentication via `launchpadlib`, credentials cached to
  `~/.lpadlib/lpad-credentials`.
- Colour output with automatic disabling on non-TTY or `NO_COLOR`. `col.error`
  checks `sys.stderr.isatty()` independently.
- `KeyboardInterrupt` (Ctrl+C) caught at the top level with a clean message
  and exit code 130.
- Dirty-tree check before branch creation.
- `LICENSE` (GPL-3.0-or-later), `CHANGELOG.md`, `CONTRIBUTING.md`.
- GitHub Actions CI workflow (ruff + mypy + pytest on Python 3.12/3.13).
- `pre-commit` config with ruff and mypy hooks.
- Test suite: 144 pytest tests across 8 files covering pure-logic modules
  (`repo`, `branch`, `cache`, `color`, `bugs`, `templates`, `drafts`) and CLI
  smoke tests.
