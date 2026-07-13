"""Smoke tests for the lpad CLI (subprocess-based, no API calls)."""

import subprocess
import sys

import pytest


def _run_lpad(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, "-m", "lpad.main", *args],
        capture_output=True,
        text=True,
    )


class TestVersion:
    def test_version_flag(self):
        result = _run_lpad("--version")
        assert result.returncode == 0
        assert "lpad" in result.stdout
        assert "0.1.0" in result.stdout


class TestHelp:
    def test_top_level_help(self):
        result = _run_lpad("--help")
        assert result.returncode == 0
        assert "list" in result.stdout
        assert "branch" in result.stdout
        assert "report" in result.stdout
        assert "cache" in result.stdout
        assert "template" in result.stdout
        assert "draft" in result.stdout
        assert "completion" in result.stdout
        assert "info" in result.stdout

    def test_branch_help(self):
        result = _run_lpad("branch", "--help")
        assert result.returncode == 0
        assert "--sru" in result.stdout
        assert "--merge" in result.stdout
        assert "--package" in result.stdout or "-p" in result.stdout

    def test_report_help(self):
        result = _run_lpad("report", "--help")
        assert result.returncode == 0
        assert "--template" in result.stdout
        assert "--resume" in result.stdout

    @pytest.mark.parametrize(
        "sub",
        ["list", "branch", "report", "status", "subscribe", "sync"],
    )
    def test_package_flag_in_help(self, sub):
        result = _run_lpad(sub, "--help")
        assert result.returncode == 0
        assert "--package" in result.stdout

    def test_status_help_has_bug_id(self):
        result = _run_lpad("status", "--help")
        assert result.returncode == 0
        assert "bug_id" in result.stdout

    def test_open_help_has_bug_id(self):
        result = _run_lpad("open", "--help")
        assert result.returncode == 0
        assert "bug_id" in result.stdout

    def test_info_help(self):
        result = _run_lpad("info", "--help")
        assert result.returncode == 0
        assert "package" in result.stdout
        assert "--refresh" in result.stdout

    def test_draft_list_help_has_package(self):
        result = _run_lpad("draft", "list", "--help")
        assert result.returncode == 0
        assert "--package" in result.stdout


class TestMutuallyExclusive:
    def test_sru_and_merge(self):
        result = _run_lpad("branch", "--sru", "--merge")
        assert result.returncode != 0
        assert "not allowed" in result.stderr.lower() or "mutually" in result.stderr.lower()


class TestTemplateCommands:
    def test_list(self):
        result = _run_lpad("template", "list")
        assert result.returncode == 0
        assert "ubuntu" in result.stdout
        assert "sru" in result.stdout
        assert "regression" in result.stdout

    def test_show_sru(self):
        result = _run_lpad("template", "show", "sru")
        assert result.returncode == 0
        assert "[ Impact ]" in result.stdout

    def test_show_unknown(self):
        result = _run_lpad("template", "show", "nonexistent")
        assert result.returncode == 1
        assert "Error" in result.stderr


class TestDraftCommands:
    def test_list_empty(self):
        result = _run_lpad("draft", "list")
        assert result.returncode == 0
        assert "No drafts" in result.stdout


class TestCacheCommands:
    def test_list(self):
        result = _run_lpad("cache", "list")
        assert result.returncode == 0


class TestInfoCommand:
    def test_no_cache_without_refresh(self):
        result = _run_lpad("info", "nonexistent-pkg")
        assert result.returncode == 1
        assert "No fresh cache" in result.stderr
        assert "--refresh" in result.stderr

    def test_with_seeded_cache(self):
        from lpad.bugs import BugSummary
        from lpad.cache import save_cache

        bugs = [
            BugSummary(id=1, title="a", status="New", importance="High", assignee="Alice"),
            BugSummary(id=2, title="b", status="New", importance="Medium", assignee="Bob"),
            BugSummary(id=3, title="c", status="In Progress", importance="High", assignee="Alice"),
        ]
        save_cache("infopkg", bugs, status_filter=None)

        result = _run_lpad("info", "infopkg", "--all")
        assert result.returncode == 0
        assert "infopkg" in result.stdout
        assert "Total bugs:" in result.stdout
        assert "By status:" in result.stdout
        assert "New" in result.stdout
        assert "In Progress" in result.stdout
        assert "By importance:" in result.stdout
        assert "Top assignees" in result.stdout
        assert "Alice" in result.stdout

    def test_empty_cache(self):
        from lpad.cache import save_cache

        save_cache("emptypkg", [], status_filter=None)

        result = _run_lpad("info", "emptypkg", "--all")
        assert result.returncode == 0
        assert "No bugs" in result.stdout


class TestResolvePackage:
    """Unit test: _resolve_package returns the explicit -p without git."""

    def test_explicit_package_skips_git(self, monkeypatch):
        import argparse

        import lpad.repo
        from lpad.main import _resolve_package

        def _boom(*a, **kw):
            raise AssertionError("detect_source_package should not be called")

        monkeypatch.setattr(lpad.repo, "detect_source_package", _boom)

        args = argparse.Namespace(package="curl")
        assert _resolve_package(args) == "curl"

    def test_falls_back_to_detect(self, monkeypatch):
        import argparse

        import lpad.repo
        from lpad.main import _resolve_package

        monkeypatch.setattr(lpad.repo, "detect_source_package", lambda **kw: "detected-pkg")

        args = argparse.Namespace(package=None)
        assert _resolve_package(args) == "detected-pkg"


class TestCompletion:
    @pytest.mark.parametrize("shell", ["bash", "zsh", "tcsh"])
    def test_completion(self, shell):
        result = _run_lpad("completion", shell)
        assert result.returncode == 0
        assert len(result.stdout) > 0

    def test_unsupported_shell(self):
        result = _run_lpad("completion", "fish")
        assert result.returncode != 0
