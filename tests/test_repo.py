"""Tests for lpad.repo."""

from unittest.mock import MagicMock, patch

import pytest

from lpad.repo import (
    _SOURCE_PKG_RE,
    parse_bug_number_from_branch,
    parse_changelog_series,
)


class TestParseBugNumberFromBranch:
    def test_plain_lp(self):
        assert parse_bug_number_from_branch("lp1234567-fix-crash") == 1234567

    def test_series_prefix(self):
        assert parse_bug_number_from_branch("noble-lp1234567-fix-crash") == 1234567

    def test_sru_branch(self):
        assert parse_bug_number_from_branch("noble-sru-lp1234567-fix-crash") == 1234567

    def test_merge_branch(self):
        assert parse_bug_number_from_branch("merge-lp1234567-noble") == 1234567

    def test_bare_lp(self):
        assert parse_bug_number_from_branch("lp1234567") == 1234567

    def test_sru_no_series(self):
        assert parse_bug_number_from_branch("sru-lp1234567-thing") == 1234567

    def test_jammy_sru(self):
        assert parse_bug_number_from_branch("jammy-sru-lp9876543-update-patches") == 9876543

    def test_not_a_bug_branch(self):
        assert parse_bug_number_from_branch("main") is None

    def test_feature_branch(self):
        assert parse_bug_number_from_branch("feature/foo") is None

    def test_lp_no_digits(self):
        assert parse_bug_number_from_branch("lp-stuff") is None

    def test_empty_string(self):
        assert parse_bug_number_from_branch("") is None


class TestSourcePkgRe:
    @pytest.mark.parametrize(
        "url,expected",
        [
            ("git+ssh://git.launchpad.net/~user/ubuntu/+source/curl", "curl"),
            ("https://git.launchpad.net/~user/ubuntu/+source/curl", "curl"),
            ("git+ssh://git.launchpad.net/ubuntu/+source/curl", "curl"),
            ("git+ssh://git.launchpad.net/~user/ubuntu/+source/libcurses", "libcurses"),
            ("https://github.com/foo/bar", None),
        ],
    )
    def test_match(self, url, expected):
        if expected is None:
            assert _SOURCE_PKG_RE.search(url) is None
        else:
            m = _SOURCE_PKG_RE.search(url)
            assert m is not None
            assert m.group(1) == expected


class TestParseChangelogSeries:
    def test_extracts_series(self, tmp_path, monkeypatch):
        changelog = tmp_path / "debian" / "changelog"
        changelog.parent.mkdir(parents=True)
        changelog.write_text(
            "curl (8.5.0-2ubuntu1) noble; urgency=medium\n\n  * Fix TLS handshake.\n"
        )
        with patch("lpad.repo.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(stdout=str(tmp_path), returncode=0)
            result = parse_changelog_series()
        assert result == "noble"

    def test_missing_file(self, tmp_path, monkeypatch):
        with patch("lpad.repo.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(stdout=str(tmp_path), returncode=0)
            result = parse_changelog_series()
        assert result is None

    def test_skips_team_header(self, tmp_path, monkeypatch):
        changelog = tmp_path / "debian" / "changelog"
        changelog.parent.mkdir(parents=True)
        changelog.write_text("[ Some Team ]\ncurl (8.5.0-2ubuntu1) jammy; urgency=medium\n")
        with patch("lpad.repo.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(stdout=str(tmp_path), returncode=0)
            result = parse_changelog_series()
        assert result == "jammy"

    def test_git_not_available(self, monkeypatch):
        import subprocess

        with patch("lpad.repo.subprocess.run", side_effect=subprocess.CalledProcessError(1, "git")):
            result = parse_changelog_series()
        assert result is None
