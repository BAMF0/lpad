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

    def test_branch_help(self):
        result = _run_lpad("branch", "--help")
        assert result.returncode == 0
        assert "--sru" in result.stdout
        assert "--merge" in result.stdout

    def test_report_help(self):
        result = _run_lpad("report", "--help")
        assert result.returncode == 0
        assert "--template" in result.stdout
        assert "--resume" in result.stdout


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


class TestCompletion:
    @pytest.mark.parametrize("shell", ["bash", "zsh", "tcsh"])
    def test_completion(self, shell):
        result = _run_lpad("completion", shell)
        assert result.returncode == 0
        assert len(result.stdout) > 0

    def test_unsupported_shell(self):
        result = _run_lpad("completion", "fish")
        assert result.returncode != 0
