import json
from collections.abc import Callable
from pathlib import Path
from subprocess import CompletedProcess

import pytest

RunAdapter = Callable[[str | Path], CompletedProcess[str]]
RunSelected = Callable[[Path, list[str] | None], CompletedProcess[str]]


def test_reports_offender(tmp_path: Path, run_adapter: RunAdapter):
    path = tmp_path / "bad.py"
    path.write_text('value: int = "wrong"\n')
    result = run_adapter(path)
    assert result.returncode == 0, result.stderr
    findings = json.loads(result.stdout)
    assert len(findings) == 1
    assert findings[0]["tool"] == "pyrefly"
    assert findings[0]["rule_id"] == "bad-assignment"
    assert "bad-assignment" in findings[0]["tool_message"]
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
    ("source", "code"),
    [
        ("from typing import Any\nx: Any = 1\n", "explicit-any"),
        ("def identity(value):\n    return value\n", "implicit-any-parameter"),
    ],
)
def test_any_is_disallowed(tmp_path: Path, run_adapter: RunAdapter, source: str, code: str):
    path = tmp_path / "example.py"
    path.write_text(source)
    result = run_adapter(path)
    assert result.returncode == 0, result.stderr
    assert code in [f["rule_id"] for f in json.loads(result.stdout)]


def test_native_selection(tmp_path: Path, run_selected_adapter: RunSelected):
    path = tmp_path / "example.py"
    path.write_text('from typing import Any\nother: Any = 1\nvalue: int = "wrong"\n')
    unfiltered = run_selected_adapter(path, None)
    assert unfiltered.returncode == 0, unfiltered.stderr
    assert {f["rule_id"] for f in json.loads(unfiltered.stdout)} == {
        "explicit-any",
        "bad-assignment",
    }
    result = run_selected_adapter(path, ["bad-assignment"])
    assert result.returncode == 0, result.stderr
    assert [f["rule_id"] for f in json.loads(result.stdout)] == ["bad-assignment"]
