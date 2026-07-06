"""Tests for lpad.bugs (data layer and helpers, no API calls)."""

from lpad.bugs import (
    OPEN_STATUSES,
    BugSummary,
    _fetch_watches,
    _format_comment_date,
    _safe_tags,
    _strip_ansi,
)


class TestStripAnsi:
    def test_no_codes(self):
        assert _strip_ansi("hello world") == "hello world"

    def test_with_codes(self):
        assert _strip_ansi("\033[1;31mhello\033[0m world") == "hello world"

    def test_multiple_codes(self):
        assert _strip_ansi("\033[31m\033[1mfoo\033[0m\033[0m") == "foo"

    def test_empty(self):
        assert _strip_ansi("") == ""


class TestFormatCommentDate:
    def test_valid_iso(self):
        result = _format_comment_date("2024-01-15T12:00:00+00:00")
        assert "2024-01-15" in result
        assert "12:00" in result
        assert "UTC" in result

    def test_invalid(self):
        assert _format_comment_date("not a date") == "not a date"

    def test_empty(self):
        assert _format_comment_date("") == ""


class TestBugSummaryFzfLine:
    def test_contains_id(self, fake_bug):
        line = fake_bug.fzf_line()
        assert "123456" in line

    def test_contains_title(self, fake_bug):
        line = fake_bug.fzf_line()
        assert "Test bug title" in line

    def test_unassigned(self):
        bug = BugSummary(
            id=1,
            title="T",
            status="New",
            importance="High",
            assignee=None,
        )
        line = bug.fzf_line()
        assert "unassigned" in line


class TestFetchWatches:
    def test_normal_watch(self):
        bug = type("FakeBug", (), {"bug_watches": []})()
        # Empty watches → empty list
        assert _fetch_watches(bug) == []

    def test_watch_raising_on_attribute(self):
        """If a watch attribute raises, _fetch_watches should skip gracefully."""

        class BadWatch:
            @property
            def url(self):
                raise RuntimeError("boom")

            @property
            def title(self):
                return "title"

            @property
            def remote_bug(self):
                return "123"

            @property
            def remote_status(self):
                return "open"

            @property
            def remote_importance(self):
                return "normal"

            @property
            def date_last_changed(self):
                return None

        class FakeBug:
            bug_watches = [BadWatch()]

        # The whole watch entry is skipped because url raises in the
        # try/except block inside _fetch_watches
        result = _fetch_watches(FakeBug())
        assert result == []

    def test_watch_with_date_last_changed(self):
        class GoodWatch:
            url = "http://example.com"
            title = "Example"
            remote_bug = "123"
            remote_status = "open"
            remote_importance = "normal"
            date_last_changed = "2024-01-01T00:00:00+00:00"

        class FakeBug:
            bug_watches = [GoodWatch()]

        result = _fetch_watches(FakeBug())
        assert len(result) == 1
        assert result[0].date_last_changed == "2024-01-01T00:00:00+00:00"


class TestSafeTags:
    def test_normal(self):
        class FakeBug:
            tags = ["a", "b"]

        assert _safe_tags(FakeBug()) == ["a", "b"]

    def test_tags_raising(self):
        class FakeBug:
            @property
            def tags(self):
                raise RuntimeError("private")

        assert _safe_tags(FakeBug()) == []


class TestOpenStatuses:
    def test_includes_expected(self):
        assert "New" in OPEN_STATUSES
        assert "In Progress" in OPEN_STATUSES
        assert "Fix Committed" in OPEN_STATUSES

    def test_excludes_closed(self):
        assert "Fix Released" not in OPEN_STATUSES
        assert "Invalid" not in OPEN_STATUSES
        assert "Won't Fix" not in OPEN_STATUSES
