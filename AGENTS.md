# AGENTS.md — lpad codebase guide

`lpad` is a focused CLI tool for Ubuntu package maintainers working with
Launchpad bugs. It wraps the official `launchpadlib` REST API client and
surfaces the most common workflows (browse, status, branch, comment, sync)
directly from the terminal, with an `fzf` picker and a local JSON cache to
avoid redundant API calls.

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
| Cache TTL | 24 h default; override with `LPAD_CACHE_TTL` env var (seconds) |
| Test suite | None |
| External binary | `fzf` (must be on PATH for `list`, `branch`, `subscribe`) |

---

## Module map

```
src/lpad/
  auth.py    OAuth login → returns authenticated Launchpad instance
  bugs.py    All data models, API fetch logic, display/print functions
  cache.py   Read / write / invalidate the JSON caches; imports from bugs.py
  color.py   ANSI escape helpers; auto-disabled on non-TTY stdout or NO_COLOR
  main.py    argparse setup; one cmd_* function per subcommand
  repo.py    git remote → source package detection; branch name parsing
  branch.py  git branch creation (lp<N>-<slug>)
```

---

## CLI command map

| Subcommand | Handler | Key functions called |
|---|---|---|
| `list` | `cmd_list` | `load_cache` → `get_package_bugs` → `fzf_select_bug` → `print_bug_summary` |
| `branch` | `cmd_branch` | `get_package_bugs` → `fzf_select_bug` → `create_branch` |
| `report` | `cmd_report` | `report_bug` (interactive, calls `lp.bugs.createBug`) |
| `open` | `cmd_open` | `parse_bug_number_from_branch` → `open_bug_in_browser` |
| `status` | `cmd_status` | `get_bug_by_id` → `print_bug_status` (live API, includes watches) |
| `subscribe` | `cmd_subscribe` | `get_package_bugs` → `fzf_select_bug` → `subscribe_to_bug` |
| `sync` | `cmd_sync` | `invalidate_cache` → `get_package_bugs(force_refresh=True)` → optionally refreshes comment cache for current branch's bug |
| `comments` | `cmd_comments` | `load_comment_cache` → `get_bug_comments` → `print_comments` |
| `_preview` | `cmd_preview` | Hidden; called by fzf `--preview`. Intercepted **before** argparse. Reads cache, calls `print_bug_summary`. |

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
   `print_bug_status`, or a new `_print_bug_*` helper).

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
  Falls back to interactive prompt if not found.

- **Branch naming**: `lp<bugid>-<slug>` or `<series>-lp<bugid>-<slug>` when a
  series is provided (either via `--series` or auto-detected from
  `debian/changelog`). The slug is produced by `branch.py:_slugify`
  (lowercase, hyphens, alphanumeric only).

- **Per-bug API cost during sync**: `get_package_bugs()` makes roughly two
  HTTP calls per bug (`task.bug` + `bug.bug_watches`). For packages with
  many open bugs, a cold-cache sync will be proportionally slow.
