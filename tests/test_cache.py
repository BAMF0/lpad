"""Tests for lpad.cache."""

import time

import pytest

from lpad.bugs import BugSummary, BugWatch, Comment
from lpad.cache import (
    cache_info,
    comment_cache_info,
    invalidate_cache,
    invalidate_comment_cache,
    load_cache,
    load_comment_cache,
    save_cache,
    save_comment_cache,
)


@pytest.fixture
def sample_bugs():
    return [
        BugSummary(
            id=123,
            title="Test bug",
            status="New",
            importance="High",
            assignee="Alice",
            tags=["test"],
            watches=[
                BugWatch(
                    url="https://bugs.debian.org/123",
                    title="Debian Bug #123",
                    remote_bug="123",
                    remote_status="open",
                    remote_importance="normal",
                    date_last_changed="2024-01-01T10:00:00+00:00",
                )
            ],
        ),
        BugSummary(
            id=456,
            title="Another bug",
            status="In Progress",
            importance="Medium",
            assignee=None,
            tags=[],
        ),
    ]


@pytest.fixture
def sample_comments():
    return [
        Comment(index=1, author="Bob", date="2024-01-01T12:00:00+00:00", body="First comment"),
        Comment(index=2, author="Alice", date="2024-01-02T13:00:00+00:00", body="Second comment"),
    ]


class TestBugCacheRoundTrip:
    def test_save_and_load(self, sample_bugs):
        save_cache("testpkg", sample_bugs, status_filter=["New", "In Progress"])
        loaded = load_cache("testpkg", status_filter=["New", "In Progress"])
        assert loaded is not None
        assert len(loaded) == 2
        assert loaded[0].id == 123
        assert loaded[0].title == "Test bug"
        assert loaded[0].watches[0].url == "https://bugs.debian.org/123"
        assert loaded[1].id == 456
        assert loaded[1].assignee is None

    def test_load_missing(self):
        assert load_cache("nonexistent") is None

    def test_status_filter_mismatch(self, sample_bugs):
        save_cache("testpkg", sample_bugs, status_filter=["New"])
        assert load_cache("testpkg", status_filter=["New", "In Progress"]) is None
        assert load_cache("testpkg", status_filter=None) is None

    def test_status_filter_match(self, sample_bugs):
        save_cache("testpkg", sample_bugs, status_filter=["New"])
        assert load_cache("testpkg", status_filter=["New"]) is not None

    def test_no_status_filter_matches_none(self, sample_bugs):
        save_cache("testpkg", sample_bugs, status_filter=None)
        assert load_cache("testpkg", status_filter=None) is not None
        assert load_cache("testpkg", status_filter=["New"]) is None


class TestCacheBackwardCompat:
    def test_missing_keys_use_defaults(self, tmp_path):
        """Old cache files missing newer fields should not crash."""
        import json

        import lpad.cache as cache_mod

        cache_mod.CACHE_DIR.mkdir(parents=True, exist_ok=True)
        path = cache_mod.CACHE_DIR / "oldpkg.json"
        data = {
            "cached_at": time.time(),
            "bugs": [
                {"id": 1},  # Missing all other fields
            ],
        }
        path.write_text(json.dumps(data))
        loaded = load_cache("oldpkg")
        assert loaded is not None
        assert len(loaded) == 1
        assert loaded[0].id == 1
        assert loaded[0].title == "(unknown)"
        assert loaded[0].tags == []

    def test_splat_watches_old_format(self, tmp_path):
        """Old watch dicts should load via .get() not **w."""
        import json

        import lpad.cache as cache_mod

        cache_mod.CACHE_DIR.mkdir(parents=True, exist_ok=True)
        path = cache_mod.CACHE_DIR / "oldpkg2.json"
        data = {
            "cached_at": time.time(),
            "bugs": [
                {"id": 1, "watches": [{"url": "http://example.com"}]},  # Missing fields
            ],
        }
        path.write_text(json.dumps(data))
        loaded = load_cache("oldpkg2")
        assert loaded is not None
        assert loaded[0].watches[0].url == "http://example.com"
        assert loaded[0].watches[0].title == ""


class TestCacheInvalidation:
    def test_invalidate(self, sample_bugs):
        save_cache("testpkg", sample_bugs)
        invalidate_cache("testpkg")
        assert load_cache("testpkg") is None

    def test_invalidate_nonexistent(self):
        invalidate_cache("nonexistent")  # Should not raise


class TestCacheInfo:
    def test_returns_info(self, sample_bugs):
        save_cache("testpkg", sample_bugs)
        info = cache_info("testpkg")
        assert info is not None
        assert "2 bugs" in info

    def test_missing_returns_none(self):
        assert cache_info("nonexistent") is None


class TestCommentCache:
    def test_round_trip(self, sample_comments):
        save_comment_cache(123, sample_comments)
        loaded = load_comment_cache(123)
        assert loaded is not None
        assert len(loaded) == 2
        assert loaded[0].author == "Bob"
        assert loaded[1].body == "Second comment"

    def test_load_missing(self):
        assert load_comment_cache(999) is None

    def test_invalidate(self, sample_comments):
        save_comment_cache(123, sample_comments)
        invalidate_comment_cache(123)
        assert load_comment_cache(123) is None

    def test_info(self, sample_comments):
        save_comment_cache(123, sample_comments)
        info = comment_cache_info(123)
        assert info is not None
        assert "2 comments" in info


class TestCacheTTL:
    def test_expired_cache_returns_none(self, sample_bugs):
        save_cache("testpkg", sample_bugs)
        # Manually backdate the cache
        import json

        import lpad.cache as cache_mod

        path = cache_mod.CACHE_DIR / "testpkg.json"
        data = json.loads(path.read_text())
        data["cached_at"] = time.time() - 999999  # Very old
        path.write_text(json.dumps(data))
        assert load_cache("testpkg") is None
