import json
from pathlib import Path
from subprocess import CompletedProcess
from typing import Callable

import pytest

RunAdapter = Callable[[str | Path], CompletedProcess[str]]
RunSelected = Callable[[Path, list[str] | None], CompletedProcess[str]]


def test_reports_offender(tmp_path: Path, run_adapter: RunAdapter):
    path = tmp_path / "bad.py"
    path.write_text("import os\n")
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
