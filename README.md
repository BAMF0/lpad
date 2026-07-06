# lpad

A focused CLI tool for working with Launchpad bugs. Browse, report, and branch
against Ubuntu source package bugs without leaving the terminal.

## Features

| Command | Description |
|---|---|
| `lpad list` | Browse bugs for the current source package via fzf with a live preview |
| `lpad branch` | Pick a bug and create a git branch (`lp<N>-<desc>`, `--sru`, `--merge`) |
| `lpad report` | File a new bug using `$EDITOR` with optional templates and draft saving |
| `lpad open` | Open the current branch's bug in the browser |
| `lpad status` | Print a live status summary for the current branch's bug |
| `lpad subscribe` | Subscribe yourself to a bug |
| `lpad sync` | Refresh the local bug cache |
| `lpad comments` | Show comments for a bug (current branch's or by ID) |
| `lpad cache` | Inspect and manage local caches (list, info, clear, clear-comments) |
| `lpad template` | Manage bug report templates (list, show, edit, refresh, remove) |
| `lpad draft` | Manage saved bug report drafts (list, show, remove, prune) |
| `lpad completion` | Print a shell completion script (bash, zsh, tcsh) |

## Requirements

- Python 3.12+
- [`fzf`](https://github.com/junegunn/fzf) (`sudo apt install fzf`)

## Installation

```bash
pipx install git+https://github.com/BAMF0/lpad
```

Or from a local clone:

```bash
pipx install .
```

## First run

On first use, lpad opens a browser window to authorise access to your Launchpad
account via OAuth. Credentials are cached to `~/.lpadlib/lpad-credentials` and
reused on subsequent runs.

## Usage

Run any command from inside a git repository whose remote points to a Launchpad
source package (e.g. `git+ssh://git.launchpad.net/~user/ubuntu/+source/curl`).

```bash
# Browse bugs and view a summary of the selected one
lpad list

# Create a branch for a bug
lpad branch
# → pick a bug in fzf
# → enter a short description, e.g. "fix tls handshake"
# → creates branch: lp2045432-fix-tls-handshake

# Branch directly by bug ID (skips fzf)
lpad branch 2045432

# SRU branch: <series>-sru-lp<N>-<desc>
lpad branch --sru

# Merge branch: merge-lp<N>-<series> (requires --series)
lpad branch --merge --series noble

# File a new bug with the SRU template
lpad report --template sru

# File a bug with a custom template file
lpad report --template ~/my-template.txt

# While on a bug branch:
lpad status    # print live bug summary in the terminal
lpad open      # open the bug in the browser
lpad comments  # show comments

# Shell completion
lpad completion bash > ~/.local/share/bash-completion/completions/lpad
lpad completion zsh > "${fpath[1]}/_lpad"
```

## Source package detection

lpad reads the `origin` git remote URL to detect the Ubuntu source package
automatically. If the remote is not a recognised Launchpad source package URL,
lpad will prompt you to enter the package name.

## Cache

Bugs are cached in `~/.cache/lpad/<package>.json` with a 24-hour TTL so that
`lpad list`, `lpad branch`, and `lpad subscribe` open instantly on subsequent
runs. Run `lpad sync` to force a refresh. Override the TTL by setting
`LPAD_CACHE_TTL` to a value in seconds:

```bash
LPAD_CACHE_TTL=3600 lpad list   # treat cache as stale after 1 hour
```

Use `lpad cache list` to see cached packages, and `lpad cache clear` to clear.

## Licence

GPL-3.0-or-later. See [`LICENSE`](LICENSE).
