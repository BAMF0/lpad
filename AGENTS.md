# AGENTS.md — lpad codebase guide

`lpad` is a focused CLI tool for Ubuntu package maintainers working with
Launchpad bugs. It wraps the official `launchpadlib` REST API client and
surfaces the most common workflows (browse, status, branch, comment, sync,
report) directly from the terminal, with an `fzf` picker, an `$EDITOR`-based
report/draft flow, and a local JSON cache to avoid redundant API calls.

---

## Quick facts

| Item | Value |
|---|---|
| Entry point | `lpad.main:main` (registered via `[project.scripts]` in `pyproject.toml`) |
| Python | 3.12+ |
| Package manager | `uv` (`uv run lpad …` or activate `.venv`) |
| Launchpad API | `launchpadlib` 2.1.0, API version `devel` |
| Auth credentials | `~/.lpadlib/lpad-credentials` (plain file, OAuth) |
| Cache root | `~/.cache/lpad/` |
| Templates dir | `~/.config/lpad/templates/` (user overrides; built-ins ship in `templates.py`) |
| Drafts dir | `~/.local/share/lpad/drafts/<package>/` (WIP bug reports) |
| Cache TTL | 24 h default; override with `LPAD_CACHE_TTL` env var (seconds) |
| Test suite | `pytest` (168 tests); run with `uv run pytest` |
| Lint | `uv run ruff check` + `uv run ruff format --check` |
| Type check | `uv run mypy src` |
| External binary | `fzf` (must be on PATH for `list`, `branch`, `subscribe`) |
| Licence | GPL-3.0-or-later |

---

## Module map

```
src/lpad/
  auth.py       OAuth login → returns authenticated Launchpad instance
  bugs.py       Data models, API fetch logic, display/print functions
  cache.py      Read / write / invalidate the JSON caches; imports from bugs.py
  color.py      ANSI escape helpers; auto-disabled on non-TTY stdout/stderr or NO_COLOR
  repo.py       git remote → source package detection; branch name parsing; changelog series
  branch.py     git branch creation (lp<N>-<slug>, SRU, merge variants); dirty-tree check
  editor.py     $EDITOR-on-temp-file flow for editing templated/draft content
  templates.py  Built-in + user override bug report templates; web refresh for SRU
  drafts.py     Work-in-progress bug report drafts (short-hash IDs, prune, resume)
  main.py       argparse setup; one cmd_* function per subcommand; KeyboardInterrupt handler
  tests/        pytest suite (168 tests); pure-logic modules have high coverage
```

---

## CLI command map

| Subcommand | Handler | Key functions called |
|---|---|---|
| `list` | `cmd_list` | `_resolve_package` → `load_cache` → `get_package_bugs` (status-filtered) → `fzf_select_bug` → `print_bug_summary` |
| `branch` | `cmd_branch` | `_resolve_package` → (positional `bug_id` or `fzf_select_bug`) → `create_branch` (kind: normal/sru/merge) |
| `report` | `cmd_report` | `_resolve_package` → `resolve_template` → `open_editor` → optional `create_draft`/`update_draft` → `lp.bugs.createBug` → optional draft removal |
| `open` | `cmd_open` | (optional `bug_id` or `parse_bug_number_from_branch`) → `open_bug_in_browser` |
| `status` | `cmd_status` | (optional `bug_id` or `parse_bug_number_from_branch`) → `get_bug_by_id` → `print_bug_status` (live API, includes watches) |
| `subscribe` | `cmd_subscribe` | `_resolve_package` → (positional `bug_id` or `fzf_select_bug`) → `subscribe_to_bug` |
| `sync` | `cmd_sync` | `_resolve_package` → `invalidate_cache` → `get_package_bugs(force_refresh=True)` → optionally refreshes comment cache for current branch's bug |
| `comments` | `cmd_comments` | `load_comment_cache` → `get_bug_comments` → `print_comments` |
| `info` | `cmd_info` | `load_cache` (or `get_package_bugs` with `--refresh`) → `print_package_dashboard` |
| `cache` | `cmd_cache` | `cache list`/`info`/`clear`/`clear-comments` (subactions) |
| `template` | `cmd_template` | `template list`/`show`/`edit`/`refresh`/`remove` (subactions) |
| `draft` | `cmd_draft` | `draft list` (optional `-p`) /`show`/`remove`/`prune` (subactions) |
| `completion` | `cmd_completion` | `shtab.complete(parser, shell=...)` for bash/zsh/tcsh |
| `_preview` | `cmd_preview` | Hidden; called by fzf `--preview`. Intercepted **before** argparse. Reads cache, calls `print_bug_summary`. |

### Package override (`-p` / `--package`)

`list`, `branch`, `report`, `status`, `subscribe`, `sync`, and
`draft list` accept `-p <pkg>` / `--package <pkg>`. When set, the package
name is used directly, bypassing `detect_source_package()` (git-remote
detection). This enables read-only browsing and cache access from outside
a source tree checkout. When absent, `detect_source_package()` is called
as before (or non-interactively in `status`, where failure yields
bug-level status without a matched Ubuntu task).

### Optional `bug_id` positionals

`open` and `status` accept an optional `bug_id` positional. When given,
the bug is looked up directly — no git repo or branch parsing required.
When omitted, both fall back to parsing the current git branch (existing
behaviour). `status` without `-p` and without a git repo shows bug-level
status only (no Ubuntu task matching).

### Status filter

`list`, `branch`, `subscribe`, and `info` accept `--status=<csv>` and
`--all` flags (mutually exclusive). Default: open statuses only (see
`OPEN_STATUSES` in `bugs.py`). The chosen filter is recorded in the cache
file under `status_filter`; switching filters triggers a refetch.

---

## Data models (`bugs.py`)

All three are plain `@dataclass` types — no ORM, serialised manually in
`cache.py`.

```python
@dataclass
class Comment:
    index: int          # 1-based; message[0] (description) is skipped
    author: str
    date: str           # ISO 8601 string from Launchpad
    body: str

@dataclass
class BugWatch:
    url: str            # direct link to the remote bug
    title: str          # e.g. "Debian Bug tracker #1048291"
    remote_bug: str     # bug number/ID in the external tracker
    remote_status: str  # raw status string from the remote tracker
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
```

`fzf_line()` on `BugSummary` formats the one-line fzf entry (coloured). It
does not include watches — those appear only in the detail / status views.

---

## Cache file layout

### `~/.cache/lpad/<package>.json` — bug list

```json
{
  "cached_at": 1748000000.0,
  "bugs": [
    {
      "id": 2045432,
      "title": "curl crashes on TLS handshake",
      "status": "In Progress",
      "importance": "High",
      "assignee": "Alice",
      "tags": ["tls", "regression"],
      "watches": [
        {
          "url": "https://bugs.debian.org/1048291",
          "title": "Debian Bug tracker #1048291",
          "remote_bug": "1048291",
          "remote_status": "open",
          "remote_importance": "",
          "date_last_changed": "2024-09-01T10:32:00+00:00"
        }
      ]
    }
  ]
}
```

### `~/.cache/lpad/comments/<bug_id>.json` — comments

```json
{
  "cached_at": 1748000000.0,
  "bug_id": 2045432,
  "comments": [
    { "index": 1, "author": "Bob", "date": "2024-01-01T12:00:00+00:00", "body": "..." }
  ]
}
```

**Backward-compat rule**: always use `.get("field", default)` when reading
individual keys from a cached dict. Never splat `**b` directly into a
dataclass constructor — new fields won't exist in old cache files.

The bug list cache also stores `status_filter` (a sorted list or `null`).
`load_cache()` compares the requested filter against the cached one and
returns `None` (cache miss) on mismatch, forcing a refetch.

---

## Templates (`templates.py`)

Built-in bug report templates (`ubuntu`, `sru`, `regression`) ship as
constants in `BUILTIN_TEMPLATES`. The SRU template mirrors the canonical
layout from ubuntu.com with `[ Impact ]`, `[ Test Plan ]`,
`[ Where problems could occur ]`, `[ Other Info ]` sections.

User overrides live in `~/.config/lpad/templates/<name>.txt` and take
precedence over built-ins. `lpad template refresh sru` fetches the latest
SRU template from
`https://ubuntu.com/project/docs/SRU/reference/bug-template/` and writes a
user override; built-ins are always available offline as a snapshot.

`resolve_template(arg)` is the entry point used by `cmd_report`: it
accepts a built-in name, a user override name, or a file path (detected
by `/` or a `.txt`/`.md` suffix), and returns the seed content.

---

## Drafts (`drafts.py`)

WIP bug reports are stored in `~/.local/share/lpad/drafts/<package>/<id>.md`
where `<id>` is the first 4 chars of a SHA1 hash of
`f"{created_at}:{package}:{title}"` — short, unique within a package, and
easy to type for `lpad report --resume=<id>`.

Each draft file begins with `Title: <title>\n\n` followed by the
description body. `update_draft()` writes back edited content in place.

`prune_drafts(older_than_days, dry_run)` is used by `lpad draft prune` to
clean up stale drafts.

---

## Editor flow (`editor.py`)

`open_editor(seed_content, suffix)` is the single entry point used by
`cmd_report` and `cmd_template edit`. It:

1. Resolves the editor: `$VISUAL` → `$EDITOR` → `sensible-editor` →
   `nano` → `vi` (first found on PATH via `shutil.which`).
2. Writes the seed to a `mkstemp` temp file under
   `~/.local/share/lpad/tmp/`.
3. Invokes the editor via `subprocess.call([editor, tmpfile])`.
4. Reads the content back and returns it (or `None` if empty).
5. Removes the temp file in a `finally` block.

The caller decides what to do with `None` (abort) vs non-empty content
(submit / save draft / save template).

---

## launchpadlib access patterns

`launchpadlib` objects are lazy: almost every attribute access triggers an
HTTP GET to the Launchpad REST API.

| Pattern | What it does |
|---|---|
| `lp.bugs[bug_id]` | Direct bug lookup by ID |
| `ubuntu.getSourcePackage(name=pkg).searchTasks()` | Paged iterator of bug tasks for an Ubuntu source package |
| `task.bug` | Lazy-loads the full bug object (one HTTP call per task) |
| `bug.bug_tasks` | All LP tasks for the bug, across all targets |
| `bug.bug_watches` | Paged collection of remote bug watches (one HTTP call) |
| `bug.messages` | Paged collection of comments (message[0] is the description) |

Always wrap attribute accesses in `try/except Exception` — LP objects can
raise for private bugs, deleted resources, or transient API errors.

`_fetch_watches(bug)` in `bugs.py` is the canonical helper for defensive
watch extraction; copy its pattern when adding similar fetch helpers.

---

## Color system (`color.py`)

All output goes through `col.*` helpers. Colors are automatically disabled
when `stdout` is not a TTY or the `NO_COLOR` environment variable is set.

| Helper | Semantic use |
|---|---|
| `col.bug_id(text)` | Bug `#NNNNNN` identifiers |
| `col.title(text)` | Bug titles, watch titles |
| `col.label(text)` | Field labels (`URL:`, `Status:`, …) |
| `col.url(text)` | Hyperlinks |
| `col.status_color(text)` | Status strings (colour-coded by value) |
| `col.importance_color(text)` | Importance strings (colour-coded by value) |
| `col.assignee(text)` | Assignee names |
| `col.tags(text)` | Tag lists |
| `col.info(text)` | Dim/secondary info |
| `col.success(text)` | Green confirmations |
| `col.error(text)` | Bold-red errors (write to `stderr`) |
| `col.c(text, *codes)` | Raw ANSI — use only when no semantic helper fits |

---

## Conventions when extending

### Adding a field to `BugSummary`

1. Add the field to the `BugSummary` dataclass in `bugs.py` with a
   default value (e.g. `= field(default_factory=list)` or `= None`).
2. Populate it in `get_package_bugs()` inside the task loop.
3. Serialise it in `save_cache()` in `cache.py`.
4. Deserialise it in `load_cache()` using `.get("field", default)` for
   backward compatibility with existing cache files.
5. Update the relevant display function(s) (`print_bug_summary`,
   `print_bug_status`, `print_package_dashboard`, or a new
   `_print_bug_*` helper).

### Adding a new CLI subcommand

1. Write `cmd_<name>(args: argparse.Namespace) -> None` in `main.py`.
2. Add an `argparse` subparser in `main()`.
3. Register it in the `commands` dict at the bottom of `main()`.

### Display helpers

Follow the `_print_bug_*` naming pattern in `bugs.py`. Keep helpers pure
(no API calls, no cache I/O) — they receive already-fetched data.

### Cache helpers

Follow the `load_comment_cache` / `save_comment_cache` pattern in
`cache.py` for any new per-bug cache (separate file per bug ID, same TTL
logic, same `_age_string` helper).

---

## Notable gotchas

- **Hidden `_preview` subcommand**: intercepted manually in `main()` *before*
  `parser.parse_args()`. Do not add it to the argparse subparsers — it must
  stay hidden from `--help`.

- **fzf ANSI stripping**: fzf passes the first token of the selected line
  back verbatim including ANSI codes. Strip with
  `re.sub(r"\033\[[0-9;]*m", "", raw)` before parsing the bug ID.

- **Source package detection**: auto-detected from the git `origin` remote
  URL by matching `+source/<name>` (see `_SOURCE_PKG_RE` in `repo.py`).
  Falls back to an interactive prompt if not found (or returns an empty
  string when `detect_source_package(interactive=False)` is used, e.g. by
  `cmd_status`). The `-p`/`--package` flag on `list`, `branch`, `report`,
  `status`, `subscribe`, `sync`, and `draft list` bypasses detection
  entirely, enabling use outside a source tree checkout.

- **Branch naming**: depends on the branch kind, controlled by the mutually
  exclusive `--sru` / `--merge` flags:

  | Kind | Flags | Format |
  |---|---|---|
  | normal | (none) | `lp<bugid>-<slug>` or `<series>-lp<bugid>-<slug>` |
  | sru | `--sru` | `<series>-sru-lp<bugid>-<slug>` |
  | merge | `--merge` | `merge-lp<bugid>-<series>` (no slug; `--series` required) |

  For normal and SRU branches, `series` comes from `--series` or is
  auto-detected from `debian/changelog`. For merge branches, `--series` is
  mandatory (the target may differ from the changelog's current series). The
  slug is produced by `branch.py:_slugify` (lowercase, hyphens, alphanumeric
  only). `parse_bug_number_from_branch` in `repo.py` recognises all three
  forms so `open`/`status`/`sync` keep working.

- **Per-bug API cost during sync**: `get_package_bugs()` makes roughly two
  HTTP calls per bug (`task.bug` + `bug.bug_watches`). For packages with
  many open bugs, a cold-cache sync will be proportionally slow.
