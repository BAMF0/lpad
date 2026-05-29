# lpad

A focused CLI tool for working with Launchpad bugs. Browse, report, and branch
against Ubuntu source package bugs without leaving the terminal.

## Features

| Command | Description |
|---|---|
| `lpad list` | Browse all bugs for the current source package via fzf with a live preview panel |
| `lpad branch` | Pick a bug with fzf and create a `lp<N>-<description>` git branch |
| `lpad report` | File a new bug against the current source package |
| `lpad open` | Open the current branch's bug in the browser |
| `lpad status` | Print a live status summary for the current branch's bug |
| `lpad subscribe` | Subscribe yourself to a bug picked via fzf |
| `lpad sync` | Refresh the local bug cache |

## Requirements

- Python 3.12+
- [`fzf`](https://github.com/junegunn/fzf) (`sudo apt install fzf`)
- [`pipx`](https://pipx.pypa.io) for installation

## Installation

```bash
pipx install git+https://git.launchpad.net/lpad
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

# File a new bug
lpad report

# While on an lp<N>-* branch:
lpad status    # print live bug summary in the terminal
lpad open      # open the bug in the browser

# Subscribe to a bug
lpad subscribe
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
