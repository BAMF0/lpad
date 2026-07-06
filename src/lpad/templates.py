"""Bug report templates: built-ins, user overrides, and web refresh."""

import re
import sys
import urllib.request
from dataclasses import dataclass
from pathlib import Path

import lpad.color as col

TEMPLATE_DIR = Path.home() / ".config" / "lpad" / "templates"

# --- Built-in templates ------------------------------------------------------

_UBUNTU_TEMPLATE = """\
## Steps to reproduce
1.

## Expected behaviour


## Actual behaviour


## Environment
- Ubuntu release:
- Package version:
- Architecture:

## Additional context

"""

_SRU_TEMPLATE = """\
[ Impact ]

* An explanation of the effects of the bug on users and justification
  for backporting the fix to the stable release.

* In addition, it is helpful, but not required, to include an
  explanation of how the upload fixes this bug.

[ Test Plan ]

* Detailed instructions on how to reproduce the bug.

* These should allow someone who is not familiar with the affected
  package to reproduce the bug and verify that the updated package
  fixes the problem.

* If other testing is appropriate to perform before landing this
  update, this should also be described here.

[ Where problems could occur ]

* Think about what the upload changes in the software. Imagine the
  change is wrong or breaks something else: how would this show up?

* It is assumed that any SRU candidate patch is well-tested before
  upload and has a low overall risk of regression, but it's important
  to make the effort to think about what *could* happen in the event
  of a regression.

* This must never be "None" or "Low", or entirely an argument as to
  why your upload is low risk.

* This both shows the SRU team that the risks have been considered,
  and provides guidance to testers in regression-testing the SRU.

[ Other Info ]

* Anything else you think is useful to include.

* Make sure to explain any deviation from the norm, to save the SRU
  reviewer from having to infer your reasoning, possibly incorrectly.

* Anticipate questions from users, SRU, +1 maintenance, security teams
  and the Technical Board and address these questions in advance.

"""

_REGRESSION_TEMPLATE = """\
## Regression
- Worked in version:
- Broken since version:

## Steps to reproduce
1.

## Actual behaviour

## Additional context

"""

BUILTIN_TEMPLATES: dict[str, str] = {
    "ubuntu": _UBUNTU_TEMPLATE,
    "sru": _SRU_TEMPLATE,
    "regression": _REGRESSION_TEMPLATE,
}

# Templates that can be refreshed from a canonical web source.
REFETCHABLE: dict[str, str] = {
    "sru": "https://ubuntu.com/project/docs/SRU/reference/bug-template/",
}


@dataclass
class TemplateInfo:
    name: str
    source: str  # "builtin" or "user override"
    length: int


def list_templates() -> list[TemplateInfo]:
    """Return all available templates: built-ins plus user overrides."""
    result: list[TemplateInfo] = []
    seen: set[str] = set()
    if TEMPLATE_DIR.exists():
        for path in sorted(TEMPLATE_DIR.glob("*.txt")):
            name = path.stem
            try:
                length = path.stat().st_size
            except OSError:
                length = 0
            result.append(TemplateInfo(name=name, source="user override", length=length))
            seen.add(name)
    for name, content in BUILTIN_TEMPLATES.items():
        if name not in seen:
            result.append(TemplateInfo(name=name, source="builtin", length=len(content)))
    return result


def get_template(name: str) -> str | None:
    """Return template content by name.

    User overrides take priority over built-ins. Returns None if the name
    is neither a built-in nor a user override.
    """
    user_path = TEMPLATE_DIR / f"{name}.txt"
    if user_path.exists():
        try:
            return user_path.read_text(encoding="utf-8")
        except OSError:
            pass
    return BUILTIN_TEMPLATES.get(name)


def load_template_from_path(path: str) -> str:
    """Load template content from an arbitrary file path."""
    p = Path(path).expanduser()
    if not p.exists():
        print(col.error(f"Error: template file not found: {p}"), file=sys.stderr)
        sys.exit(1)
    try:
        return p.read_text(encoding="utf-8")
    except OSError as exc:
        print(col.error(f"Error: could not read template file: {exc}"), file=sys.stderr)
        sys.exit(1)


def save_user_template(name: str, content: str) -> Path:
    """Write *content* as a user override for *name*."""
    TEMPLATE_DIR.mkdir(parents=True, exist_ok=True)
    path = TEMPLATE_DIR / f"{name}.txt"
    path.write_text(content, encoding="utf-8")
    return path


def remove_user_template(name: str) -> bool:
    """Remove a user override. Returns True if removed, False if none existed."""
    path = TEMPLATE_DIR / f"{name}.txt"
    if path.exists():
        path.unlink()
        return True
    return False


def resolve_template(template_arg: str | None) -> str:
    """Resolve a --template argument into template content.

    - None → empty string (no template).
    - Name of a built-in or user override → that template's content.
    - A path (contains '/' or ends with .txt/.md) → file content.
    """
    if template_arg is None:
        return ""
    if "/" in template_arg or template_arg.endswith((".txt", ".md")):
        return load_template_from_path(template_arg)
    content = get_template(template_arg)
    if content is None:
        print(
            col.error(
                f"Error: unknown template '{template_arg}'. "
                f"Available: {', '.join(sorted(BUILTIN_TEMPLATES))} or a file path."
            ),
            file=sys.stderr,
        )
        sys.exit(1)
    return content


# --- Web refresh -------------------------------------------------------------

_SECTION_RE = re.compile(r"\[\s*([^\]]+)\s*\](.*?)(?=\[\s*[^\]]+\s*\]|$)", re.DOTALL)


def refresh_template(name: str) -> str:
    """Fetch the latest version of *name* from its canonical web source.

    Writes the result to ~/.config/lpad/templates/<name>.txt and returns it.
    Exits with an error if *name* is not refreshable or the fetch fails.
    """
    url = REFETCHABLE.get(name)
    if url is None:
        refreshable = ", ".join(sorted(REFETCHABLE)) or "(none)"
        print(
            col.error(
                f"Error: template '{name}' cannot be refreshed from the web. "
                f"Refreshable: {refreshable}"
            ),
            file=sys.stderr,
        )
        sys.exit(1)

    try:
        req = urllib.request.Request(url, headers={"User-Agent": "lpad/0.1"})
        with urllib.request.urlopen(req, timeout=15) as resp:
            html = resp.read().decode("utf-8", errors="replace")
    except Exception as exc:
        print(
            col.error(f"Error: could not fetch template from {url}: {exc}"),
            file=sys.stderr,
        )
        sys.exit(1)

    content = _extract_sru_template(html)
    if not content:
        print(
            col.error(
                f"Error: could not parse the SRU template from {url}. "
                "The page structure may have changed."
            ),
            file=sys.stderr,
        )
        sys.exit(1)

    path = save_user_template(name, content)
    print(col.success(f"Refreshed template '{name}' → {path}"))
    return content


def _extract_sru_template(html: str) -> str:
    """Extract the SRU bug template body from the ubuntu.com docs HTML.

    The page contains the template as preformatted text with [ Section ]
    markers. We strip HTML tags and normalise whitespace while preserving
    the section structure.
    """
    text = re.sub(r"<[^>]+>", "", html)
    text = _html_unescape(text)
    sections: list[str] = []
    for m in _SECTION_RE.finditer(text):
        header = m.group(1).strip()
        body = m.group(2).strip()
        if header in ("Impact", "Test Plan", "Where problems could occur", "Other Info"):
            lines = [f"[ {header} ]", ""]
            for raw_line in body.splitlines():
                line = raw_line.rstrip()
                if line.strip():
                    lines.append(line)
            lines.append("")
            sections.append("\n".join(lines))
    if not sections:
        return ""
    return "\n".join(sections) + "\n"


def _html_unescape(text: str) -> str:
    import html as _html

    return _html.unescape(text)
