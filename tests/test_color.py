"""Tests for lpad.color."""

import io
import sys

import pytest

import lpad.color as col


class TestColorEnableDisable:
    def test_no_color_env(self, monkeypatch):
        monkeypatch.setenv("NO_COLOR", "1")
        assert col._colors_enabled() is False
        assert col._error_colors_enabled() is False

    def test_no_color_env_empty_string_disables(self, monkeypatch):
        """NO_COLOR presence (even empty) disables colours per spec."""
        monkeypatch.setenv("NO_COLOR", "")
        assert col._colors_enabled() is False

    def test_no_color_unset_tty(self, monkeypatch):
        monkeypatch.delenv("NO_COLOR", raising=False)
        monkeypatch.setattr(sys, "stdout", io.StringIO())
        monkeypatch.setattr(sys, "stderr", io.StringIO())
        assert col._colors_enabled() is False
        assert col._error_colors_enabled() is False


class TestStatusColor:
    def test_known_status(self, monkeypatch):
        monkeypatch.delenv("NO_COLOR", raising=False)
        monkeypatch.setattr(sys, "stdout", io.StringIO())
        sys.stdout.isatty = lambda: True
        monkeypatch.setattr(sys, "stderr", io.StringIO())
        sys.stderr.isatty = lambda: True
        assert col.status_color("New") != "New"  # Should be wrapped in ANSI

    def test_unknown_status_passthrough(self):
        assert col.status_color("Bogus") == "Bogus"

    def test_case_insensitive(self, monkeypatch):
        monkeypatch.delenv("NO_COLOR", raising=False)
        monkeypatch.setattr(sys, "stdout", io.StringIO())
        sys.stdout.isatty = lambda: True
        monkeypatch.setattr(sys, "stderr", io.StringIO())
        sys.stderr.isatty = lambda: True
        assert col.status_color("new") != "new"
        assert col.status_color("NEW") != "NEW"

    @pytest.mark.parametrize(
        "status",
        [
            "New",
            "Confirmed",
            "Triaged",
            "In Progress",
            "Fix Committed",
            "Fix Released",
            "Invalid",
            "Won't Fix",
            "Expired",
        ],
    )
    def test_all_known_statuses_colored(self, status, monkeypatch):
        monkeypatch.setattr(sys, "stdout", io.StringIO())
        sys.stdout.isatty = lambda: True
        monkeypatch.setattr(sys, "stderr", io.StringIO())
        sys.stderr.isatty = lambda: True
        monkeypatch.delenv("NO_COLOR", raising=False)
        assert col.status_color(status) != status


class TestImportanceColor:
    def test_known_importance(self, monkeypatch):
        monkeypatch.delenv("NO_COLOR", raising=False)
        monkeypatch.setattr(sys, "stdout", io.StringIO())
        sys.stdout.isatty = lambda: True
        monkeypatch.setattr(sys, "stderr", io.StringIO())
        sys.stderr.isatty = lambda: True
        assert col.importance_color("Critical") != "Critical"

    def test_unknown_importance_passthrough(self):
        assert col.importance_color("Bogus") == "Bogus"

    @pytest.mark.parametrize(
        "imp",
        [
            "Critical",
            "High",
            "Medium",
            "Low",
            "Wishlist",
            "Undecided",
        ],
    )
    def test_all_known_importances_colored(self, imp, monkeypatch):
        monkeypatch.setattr(sys, "stdout", io.StringIO())
        sys.stdout.isatty = lambda: True
        monkeypatch.setattr(sys, "stderr", io.StringIO())
        sys.stderr.isatty = lambda: True
        monkeypatch.delenv("NO_COLOR", raising=False)
        assert col.importance_color(imp) != imp


class TestHelpers:
    def test_c_with_no_codes(self, monkeypatch):
        monkeypatch.setattr(sys, "stdout", io.StringIO())
        sys.stdout.isatty = lambda: True
        monkeypatch.delenv("NO_COLOR", raising=False)
        assert col.c("hello") == "hello"

    def test_c_with_codes(self, monkeypatch):
        monkeypatch.setattr(sys, "stdout", io.StringIO())
        sys.stdout.isatty = lambda: True
        monkeypatch.delenv("NO_COLOR", raising=False)
        result = col.c("hello", col.GREEN)
        assert col.GREEN in result
        assert col.RESET in result

    def test_error_checks_stderr(self, monkeypatch):
        monkeypatch.delenv("NO_COLOR", raising=False)
        monkeypatch.setattr(sys, "stdout", io.StringIO())
        sys.stdout.isatty = lambda: True  # stdout is TTY
        monkeypatch.setattr(sys, "stderr", io.StringIO())
        sys.stderr.isatty = lambda: False  # stderr is not TTY
        assert col.error("oops") == "oops"  # No ANSI codes
