import json
from collections.abc import Callable
from pathlib import Path
from subprocess import CompletedProcess

import pytest
from pydantic import JsonValue

RunAdapter = Callable[[str | Path], CompletedProcess[str]]
RunSelected = Callable[[Path, list[str] | None], CompletedProcess[str]]
RunConfigured = Callable[[Path, dict[str, JsonValue]], CompletedProcess[str]]


def test_reports_offender(write_file: Callable[[str, str], Path], run_adapter: RunAdapter):
    path = write_file("bad.py", "import os\n")
    result = run_adapter(path)
    assert result.returncode == 0, result.stderr
    findings = json.loads(result.stdout)
    assert len(findings) == 1
    assert findings[0]["tool"] == "ruff"
    assert findings[0]["rule_id"] == "F401"
    assert "F401" in findings[0]["tool_message"]
    assert Path(findings[0]["filename"]).resolve() == path
    assert findings[0]["location"]["row"] == 1


def test_clean_file(tmp_path: Path, run_adapter: RunAdapter):
    path = tmp_path / "clean.py"
    path.write_text("value: int = 1\n")
    result = run_adapter(path)
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout) == []


def test_command_error(run_adapter: RunAdapter):
    result = run_adapter("--nonexistent-option")
    assert result.returncode != 0
    assert result.stdout == ""
    assert result.stderr


@pytest.mark.parametrize(
    ("comment", "expected"),
    [("# noqa", ["PGH004"]), ("# noqa: F401", []), ("# ruff: noqa", ["PGH004"])],
)
def test_blanket_suppressions_only(
    tmp_path: Path, run_selected_adapter: RunSelected, comment: str, expected: list[str]
):
    path = tmp_path / "example.py"
    path.write_text(f"{comment}\nimport os\n" if "ruff:" in comment else f"import os  {comment}\n")
    result = run_selected_adapter(path, ["PGH004"])
    assert result.returncode == 0, result.stderr
    assert [f["rule_id"] for f in json.loads(result.stdout)] == expected


def test_native_selection_excludes_other_rules(tmp_path: Path, run_selected_adapter: RunSelected):
    path = tmp_path / "example.py"
    path.write_text("import os\n")
    result = run_selected_adapter(path, ["E501"])
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout) == []


@pytest.mark.parametrize(
    ("selectors", "expected"),
    [
        (["F"], "F"),
        (["F", "F4"], "F4"),
        (["F", "F4", "F401"], "F401"),
        (["F401", "F4", "F"], "F401"),
    ],
)
def test_most_specific_selector_wins(
    tmp_path: Path, run_selected_adapter: RunSelected, selectors: list[str], expected: str
):
    path = tmp_path / "example.py"
    path.write_text("import os\n")
    result = run_selected_adapter(path, selectors)
    assert result.returncode == 0, result.stderr
    findings = json.loads(result.stdout)
    assert [f["rule_id"] for f in findings] == [expected]
    assert findings[0]["tool_message"].startswith("F401:")


def test_specificity_across_function_selections(
    tmp_path: Path, run_configured_adapter: RunConfigured
):
    path = tmp_path / "example.py"
    path.write_text("import os\n")
    result = run_configured_adapter(
        path,
        {
            "config": {},
            "selections": [
                {"rules": ["F"], "config": {}},
                {"rules": ["F401"], "config": {}},
            ],
        },
    )
    assert result.returncode == 0, result.stderr
    assert [f["rule_id"] for f in json.loads(result.stdout)] == ["F401"]


@pytest.mark.parametrize(
    "source",
    [
        "import dataclasses\n",
        "from dataclasses import dataclass\n",
        "from pydantic.dataclasses import dataclass\n",
        "from pydantic import dataclasses\n",
    ],
)
def test_banned_api_configuration(
    tmp_path: Path, run_configured_adapter: RunConfigured, source: str
):
    path = tmp_path / "example.py"
    path.write_text(source)
    result = run_configured_adapter(
        path,
        {
            "config": {},
            "selections": [
                {
                    "rules": ["TID251"],
                    "config": {
                        "flake8-tidy-imports": {
                            "banned-api": {
                                "dataclasses": {"msg": "Use Pydantic BaseModel."},
                                "pydantic.dataclasses": {"msg": "Use Pydantic BaseModel."},
                            }
                        }
                    },
                }
            ],
        },
    )
    assert result.returncode == 0, result.stderr
    findings = json.loads(result.stdout)
    assert len(findings) == 1
    assert findings[0]["rule_id"] == "TID251"
    assert "Use Pydantic BaseModel." in findings[0]["tool_message"]


def test_tool_and_function_configuration(tmp_path: Path, run_configured_adapter: RunConfigured):
    path = tmp_path / "example.py"
    path.write_text(
        "def test(a: bool, b: bool, c: bool) -> None:\n    if a and b and c:\n        pass\n"
    )
    result = run_configured_adapter(
        path,
        {
            "config": {"preview": True},
            "selections": [
                {
                    "rules": ["PLR0916"],
                    "config": {"pylint": {"max-bool-expr": 2}},
                }
            ],
        },
    )
    assert result.returncode == 0, result.stderr
    assert [f["rule_id"] for f in json.loads(result.stdout)] == ["PLR0916"]


def test_conflicting_configuration_is_an_error(
    tmp_path: Path, run_configured_adapter: RunConfigured
):
    path = tmp_path / "example.py"
    path.write_text("value = 1\n")
    result = run_configured_adapter(
        path,
        {
            "config": {},
            "selections": [
                {"rules": ["PLR0916"], "config": {"pylint": {"max-bool-expr": 2}}},
                {"rules": ["PLR0916"], "config": {"pylint": {"max-bool-expr": 3}}},
            ],
        },
    )
    assert result.returncode != 0
    assert result.stdout == ""
    assert "Conflicting Ruff settings" in result.stderr
