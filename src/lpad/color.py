"""ANSI colour helpers for lpad terminal output.

Colours are automatically disabled when:
- stdout is not a TTY (e.g. output is piped)
- The NO_COLOR environment variable is set (https://no-color.org)
"""

import os
import sys

# ANSI codes
RESET = "\033[0m"
BOLD = "\033[1m"
DIM = "\033[2m"
RED = "\033[31m"
GREEN = "\033[32m"
YELLOW = "\033[33m"
BLUE = "\033[34m"
MAGENTA = "\033[35m"
CYAN = "\033[36m"
WHITE = "\033[37m"
BOLD_RED = "\033[1;31m"
BOLD_WHITE = "\033[1;37m"
BOLD_CYAN = "\033[1;36m"
UNDERLINE = "\033[4m"


def _colors_enabled() -> bool:
    """Return True if ANSI colour output should be used on stdout."""
    if os.environ.get("NO_COLOR"):
        return False
    return sys.stdout.isatty()


def _error_colors_enabled() -> bool:
    """Return True if ANSI colour should be used for stderr messages."""
    if os.environ.get("NO_COLOR"):
        return False
    return sys.stderr.isatty()


def c(text: str, *codes: str) -> str:
    """Wrap text in ANSI escape codes if colours are enabled."""
    if not _colors_enabled() or not codes:
        return text
    return "".join(codes) + text + RESET


# --- Convenience wrappers ---


def success(text: str) -> str:
    return c(text, GREEN)


def error(text: str) -> str:
    if not _error_colors_enabled():
        return text
    return "".join((BOLD_RED, text, RESET))


def info(text: str) -> str:
    return c(text, DIM)


def prompt(text: str) -> str:
    return c(text, BOLD)


def url(text: str) -> str:
    return c(text, CYAN, UNDERLINE)


def bug_id(text: str) -> str:
    return c(text, BOLD_CYAN)


def title(text: str) -> str:
    return c(text, BOLD_WHITE)


def label(text: str) -> str:
    return c(text, DIM)


def assignee(text: str) -> str:
    return c(text, YELLOW)


def tags(text: str) -> str:
    return c(text, MAGENTA)


def branch_name(text: str) -> str:
    return c(text, BOLD_CYAN)


# --- Semantic colour coding ---

_STATUS_COLORS: dict[str, str] = {
    "new": BLUE,
    "confirmed": CYAN,
    "triaged": CYAN,
    "in progress": YELLOW,
    "fix committed": GREEN,
    "fix released": GREEN,
    "invalid": DIM,
    "won't fix": DIM,
    "wontfix": DIM,
    "expired": DIM,
}

_IMPORTANCE_COLORS: dict[str, str] = {
    "critical": BOLD_RED,
    "high": RED,
    "medium": YELLOW,
    "low": CYAN,
    "wishlist": BLUE,
    "undecided": DIM,
}


def status_color(status: str) -> str:
    """Return the status string coloured by its value."""
    code = _STATUS_COLORS.get(status.lower())
    if code:
        return c(status, code)
    return status


def importance_color(importance: str) -> str:
    """Return the importance string coloured by its value."""
    code = _IMPORTANCE_COLORS.get(importance.lower())
    if code:
        return c(importance, code)
    return importance
