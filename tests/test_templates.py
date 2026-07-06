"""Tests for lpad.templates."""

import pytest

import lpad.templates as tmpl


class TestBuiltinTemplates:
    def test_ubuntu_exists(self):
        assert "ubuntu" in tmpl.BUILTIN_TEMPLATES
        content = tmpl.BUILTIN_TEMPLATES["ubuntu"]
        assert "Steps to reproduce" in content

    def test_sru_exists(self):
        assert "sru" in tmpl.BUILTIN_TEMPLATES
        content = tmpl.BUILTIN_TEMPLATES["sru"]
        assert "[ Impact ]" in content
        assert "[ Test Plan ]" in content
        assert "[ Where problems could occur ]" in content
        assert "[ Other Info ]" in content

    def test_regression_exists(self):
        assert "regression" in tmpl.BUILTIN_TEMPLATES
        content = tmpl.BUILTIN_TEMPLATES["regression"]
        assert "Worked in version" in content
        assert "Broken since version" in content


class TestGetTemplate:
    def test_builtin(self):
        content = tmpl.get_template("ubuntu")
        assert content is not None
        assert "Steps to reproduce" in content

    def test_unknown(self):
        assert tmpl.get_template("nonexistent") is None


class TestUserOverrides:
    def test_save_and_get(self):
        tmpl.save_user_template("custom", "Custom content here")
        content = tmpl.get_template("custom")
        assert content == "Custom content here"

    def test_override_builtin(self):
        tmpl.save_user_template("ubuntu", "My custom ubuntu template")
        content = tmpl.get_template("ubuntu")
        assert content == "My custom ubuntu template"

    def test_remove_override(self):
        tmpl.save_user_template("ubuntu", "override")
        assert tmpl.remove_user_template("ubuntu") is True
        # Should fall back to builtin
        content = tmpl.get_template("ubuntu")
        assert content == tmpl.BUILTIN_TEMPLATES["ubuntu"]

    def test_remove_nonexistent_override(self):
        assert tmpl.remove_user_template("ubuntu") is False


class TestListTemplates:
    def test_lists_builtins(self):
        templates = tmpl.list_templates()
        names = [t.name for t in templates]
        assert "ubuntu" in names
        assert "sru" in names
        assert "regression" in names

    def test_shows_user_override(self):
        tmpl.save_user_template("ubuntu", "override")
        templates = tmpl.list_templates()
        ubuntu = next(t for t in templates if t.name == "ubuntu")
        assert ubuntu.source == "user override"


class TestResolveTemplate:
    def test_none_returns_empty(self):
        assert tmpl.resolve_template(None) == ""

    def test_builtin_name(self):
        content = tmpl.resolve_template("ubuntu")
        assert "Steps to reproduce" in content

    def test_user_override_name(self):
        tmpl.save_user_template("mytmpl", "My content")
        content = tmpl.resolve_template("mytmpl")
        assert content == "My content"

    def test_file_path(self, tmp_path):
        path = tmp_path / "template.txt"
        path.write_text("File template content")
        content = tmpl.resolve_template(str(path))
        assert content == "File template content"

    def test_unknown_name_exits(self):
        with pytest.raises(SystemExit):
            tmpl.resolve_template("nonexistent")


class TestExtractSruTemplate:
    def test_extracts_sections(self):
        html = """
        <pre>
        [ Impact ]
        * Description of impact

        [ Test Plan ]
        * Steps here

        [ Where problems could occur ]
        * Risk analysis

        [ Other Info ]
        * Extra info
        </pre>
        """
        result = tmpl._extract_sru_template(html)
        assert "[ Impact ]" in result
        assert "[ Test Plan ]" in result
        assert "[ Where problems could occur ]" in result
        assert "[ Other Info ]" in result

    def test_no_sections(self):
        assert tmpl._extract_sru_template("no sections here") == ""
