"""Shared test fixtures for lpad.

Sets HOME to a temp directory *before* any lpad module is imported,
so that module-level path constants (~/.cache/lpad, etc.) point into
the test sandbox.
"""

import os
import tempfile
from pathlib import Path

import pytest

# Set HOME to a temp directory before any lpad module is imported.
# Module-level constants like CACHE_DIR are computed at import time.
_TMP_HOME = Path(tempfile.mkdtemp(prefix="lpad-test-"))
os.environ["HOME"] = str(_TMP_HOME)

# Also clear NO_COLOR so color helpers behave predictably in tests
os.environ.pop("NO_COLOR", None)


@pytest.fixture
def fake_bug():
    """Return a minimal fake bug object for testing."""
    from lpad.bugs import BugSummary

    return BugSummary(
        id=123456,
        title="Test bug title",
        status="New",
        importance="High",
        assignee="Alice",
        tags=["test", "regression"],
    )


@pytest.fixture(autouse=True)
def _clean_sandboxes():
    """Ensure each test starts with empty cache/draft/template directories."""
    import lpad.cache as cache
    import lpad.drafts as drafts
    import lpad.templates as templates

    # Clear cache dir
    if cache.CACHE_DIR.exists():
        for f in cache.CACHE_DIR.glob("*.json"):
            f.unlink()
        if cache.COMMENT_CACHE_DIR.exists():
            for f in cache.COMMENT_CACHE_DIR.glob("*.json"):
                f.unlink()

    # Clear drafts
    if drafts.DRAFT_ROOT.exists():
        import shutil

        shutil.rmtree(drafts.DRAFT_ROOT)

    # Clear user templates
    if templates.TEMPLATE_DIR.exists():
        import shutil

        shutil.rmtree(templates.TEMPLATE_DIR)

    yield
