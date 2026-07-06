# Contributing to lpad

Thanks for your interest in contributing! This is a short guide to get you up
and running.

## Development setup

```bash
git clone https://github.com/BAMF0/lpad.git
cd lpad
uv sync
```

This creates a `.venv` with all runtime + dev dependencies. Activate it or
prefix commands with `uv run`.

## Running lpad from source

```bash
uv run lpad --help
```

## Code quality

Before opening a PR, run:

```bash
uv run ruff check
uv run ruff format --check
uv run mypy src
uv run pytest
```

Or install pre-commit hooks to run them automatically:

```bash
uv run pre-commit install
pre-commit run --all-files
```

## Commit messages

Use the imperative mood (e.g. "Add SRU branch mode", not "Added"). Keep the
subject line under 72 characters. Reference issue numbers in the body if
applicable.

## Branch model

- `main` is the release branch; PRs target `main`.
- Feature branches: `feat/<short-description>`.
- Bugfix branches: `fix/<short-description>`.

## Testing

Tests live in `tests/` and use `pytest`. Pure-function modules
(`repo.py`, `branch.py`, `cache.py`, `color.py`, `templates.py`, `drafts.py`)
should have high coverage. API-touching modules (`bugs.py`, `auth.py`) are
tested via mocks where feasible; full integration tests against Launchpad are
out of scope for CI.

```bash
uv run pytest -v
uv run pytest --cov=lpad --cov-report=term-missing
```

## Adding a new CLI subcommand

1. Write `cmd_<name>(args: argparse.Namespace) -> None` in `main.py`.
2. Add an `argparse` subparser in `_build_parser()`.
3. Register it in the `commands` dict in `main()`.
4. Add tests in `tests/`.
5. Update `AGENTS.md` and `README.md`.

## Licence

By contributing, you agree that your contributions will be licensed under the
GPL-3.0-or-later licence.
