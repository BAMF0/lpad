# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.1.0] - 2026-07-06

### Added

- **Branch creation modes**: `--sru` (SRU branch: `<series>-sru-lp<N>-<desc>`) and
  `--merge` (merge branch: `merge-lp<N>-<series>`) mutually exclusive flags on
  `lpad branch`.
- **Positional bug ID**: `lpad branch <bug_id>` and `lpad subscribe <bug_id>` skip
  the fzf picker for scripting / quick use.
- **Status filter**: `lpad list`, `lpad branch`, and `lpad subscribe` default to
  open-statuses only. Use `--all` or `--status=New,In Progress` to override.
- **Bug report templates**: `lpad report --template=<name|path>` seeds `$EDITOR`
  with a built-in (`ubuntu`, `sru`, `regression`) or custom file template.
- **Template management**: `lpad template` subcommand group (list, show, edit,
  refresh, remove). `lpad template refresh sru` fetches the latest SRU template
  from ubuntu.com.
- **Draft workflow**: `lpad report --save`-style flow — reports are opened in
  `$EDITOR`, can be saved as drafts, resumed later, and deleted after submission.
  `lpad draft` subcommand group (list, show, remove, prune).
- **Cache management**: `lpad cache` subcommand group (list, info, clear,
  clear-comments).
- **Shell completion**: `lpad completion {bash,zsh,fish}` prints a completion
  script via `shtab`.
- **`--version` flag** on the top-level parser.
- **`lpad comments`** subcommand (already existed, now documented).
- GitHub Actions CI workflow (ruff + mypy + pytest on Python 3.12/3.13).
- `LICENSE` (GPL-3.0-or-later), `CHANGELOG.md`, `CONTRIBUTING.md`.
- `pre-commit` config with ruff and mypy hooks.

### Changed

- `lpad report` now opens `$EDITOR` on a temp file instead of using the
  Ctrl+D `input()` loop. Falls back to `--no-editor` (stdin) for scripting.
- `get_package_bugs` now accepts a `status` parameter (default: open statuses).
- Cache files store the status filter used; switching filters triggers a refetch.
- `print_bug_status` task matching tightened to avoid false-positive substring
  matches (e.g. `curl` matching `libcurses`).
- Branch-name hints in `open`, `status`, `sync`, `comments` updated to mention
  all four branch forms (`lp<N>-*`, `<series>-lp<N>-*`, `<series>-sru-lp<N>-*`,
  `merge-lp<N>-<series>`).
- `color.py` `col.error()` now checks `sys.stderr.isatty()` instead of stdout.
- `_check_fzf` uses `shutil.which("fzf")` instead of shelling out to `which`.
- Hoisted lazy `import re` / `import os` / `from datetime import ...` to module
  tops in `bugs.py` and `repo.py`.

### Fixed

- Removed duplicate `parse_changelog_series` definition in `repo.py` (second
  definition silently shadowed the first).
- `get_bug_by_id` now catches `NotFound`/`Unauthorized` and exits with a clear
  error instead of a raw traceback.
- `subscribe_to_bug` and `report_bug` wrap Launchpad API calls in try/except
  with clear error messages.
- `print_bug_status` reads `bug.title`, `bug.tags`, `bug.description`, `bug.heat`
  defensively — private or deleted bugs no longer crash.
- `cache.py` `load_cache` now uses `.get()` with defaults for all mandatory
  keys, hardening against partial cache corruption.
- `KeyboardInterrupt` (Ctrl+C) is now caught at the top level with a clean
  `Interrupted.` message and exit code 130.
- Branch creation checks for a clean working tree before `git checkout -b`.
