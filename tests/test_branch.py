"""Tests for lpad.branch."""

from unittest.mock import MagicMock, patch

import pytest

from lpad.branch import _check_clean_worktree, _slugify, create_branch


class TestSlugify:
    def test_simple(self):
        assert _slugify("fix crash on startup") == "fix-crash-on-startup"

    def test_uppercase(self):
        assert _slugify("Fix TLS Handshake") == "fix-tls-handshake"

    def test_underscores(self):
        assert _slugify("fix_thing_now") == "fix-thing-now"

    def test_special_chars(self):
        assert _slugify("fix @#$ crash!!!") == "fix-crash"

    def test_collapses_hyphens(self):
        assert _slugify("fix  --  crash") == "fix-crash"

    def test_strips_leading_trailing(self):
        assert _slugify("  --- fix crash ---  ") == "fix-crash"

    def test_empty(self):
        assert _slugify("") == ""

    def test_only_special(self):
        assert _slugify("@#$!!!") == ""


class TestCreateBranchNormal:
    def test_plain(self):
        with (
            patch("builtins.input", return_value="fix crash"),
            patch("lpad.branch.subprocess.run") as mock_run,
            patch("lpad.branch._check_clean_worktree"),
        ):
            create_branch(12345, series=None, kind="normal")
        mock_run.assert_called_once_with(["git", "checkout", "-b", "lp12345-fix-crash"], check=True)

    def test_with_series(self):
        with (
            patch("builtins.input", return_value="fix crash"),
            patch("lpad.branch.subprocess.run") as mock_run,
            patch("lpad.branch._check_clean_worktree"),
        ):
            create_branch(12345, series="noble", kind="normal")
        mock_run.assert_called_once_with(
            ["git", "checkout", "-b", "noble-lp12345-fix-crash"], check=True
        )


class TestCreateBranchSru:
    def test_sru(self):
        with (
            patch("builtins.input", return_value="fix tls"),
            patch("lpad.branch.subprocess.run") as mock_run,
            patch("lpad.branch._check_clean_worktree"),
        ):
            create_branch(12345, series="noble", kind="sru")
        mock_run.assert_called_once_with(
            ["git", "checkout", "-b", "noble-sru-lp12345-fix-tls"], check=True
        )

    def test_sru_no_series_exits(self):
        with (
            patch("builtins.input", return_value="fix tls"),
            patch("lpad.branch.subprocess.run"),
            pytest.raises(SystemExit),
        ):
            create_branch(12345, series=None, kind="sru")


class TestCreateBranchMerge:
    def test_merge(self):
        with (
            patch("lpad.branch.subprocess.run") as mock_run,
            patch("lpad.branch._check_clean_worktree"),
        ):
            create_branch(12345, series="noble", kind="merge")
        mock_run.assert_called_once_with(
            ["git", "checkout", "-b", "merge-lp12345-noble"], check=True
        )

    def test_merge_no_series_exits(self):
        with patch("lpad.branch.subprocess.run"), pytest.raises(SystemExit):
            create_branch(12345, series=None, kind="merge")

    def test_merge_no_description_prompt(self):
        """Merge branches should not prompt for a description."""
        with (
            patch("builtins.input", side_effect=AssertionError("should not prompt")),
            patch("lpad.branch.subprocess.run"),
            patch("lpad.branch._check_clean_worktree"),
        ):
            create_branch(12345, series="noble", kind="merge")


class TestCreateBranchEmptyDescription:
    def test_empty_desc_exits(self):
        with (
            patch("builtins.input", return_value=""),
            patch("lpad.branch.subprocess.run"),
            pytest.raises(SystemExit),
        ):
            create_branch(12345, series=None, kind="normal")

    def test_whitespace_only_desc_exits(self):
        with (
            patch("builtins.input", return_value="   "),
            patch("lpad.branch.subprocess.run"),
            pytest.raises(SystemExit),
        ):
            create_branch(12345, series=None, kind="normal")


class TestCheckCleanWorktree:
    def test_clean(self):
        with patch("lpad.branch.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(stdout="", returncode=0)
            _check_clean_worktree()

    def test_dirty_exits(self):
        with patch("lpad.branch.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(stdout=" M file.py\n", returncode=0)
            with pytest.raises(SystemExit):
                _check_clean_worktree()

    def test_not_git_repo_exits(self):
        import subprocess

        err = subprocess.CalledProcessError(1, "git")
        with patch("lpad.branch.subprocess.run", side_effect=err), pytest.raises(SystemExit):
            _check_clean_worktree()
