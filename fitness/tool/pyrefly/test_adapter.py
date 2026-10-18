import json
from collections.abc import Callable
from pathlib import Path
from subprocess import CompletedProcess

import pytest
from pydantic import JsonValue

RunAdapter = Callable[[str | Path], CompletedProcess[str]]
RunSelected = Callable[[Path, list[str] | None], CompletedProcess[str]]
Batch = tuple[Path, dict[str, str]]
RunBatch = Callable[[dict[str, str], dict[str, JsonValue]], Batch]

pytestmark = pytest.mark.xdist_group("pyrefly_native_examples")

ANY_EXAMPLES = [
    ("from typing import Any\nx: Any = 1\n", "explicit-any"),
    ("def identity(value):\n    return value\n", "implicit-any-parameter"),
]


@pytest.fixture(scope="module")
def native_examples(run_adapter_batch: RunBatch) -> Batch:
    examples = {
        "bad.py": 'value: int = "wrong"\n',
        "clean.py": "value: int = 1\n",
        "mixed.py": 'from typing import Any\nother: Any = 1\nvalue: int = "wrong"\n',
        **{f"{code}.py": source for source, code in ANY_EXAMPLES},
    }
    return run_adapter_batch(
        examples, {"config": {}, "selections": [{"rules": None, "config": {}}]}
    )


def test_reports_offender(native_examples: Batch):
    root, results = native_examples
    findings = json.loads(results["bad.py"])
    assert len(findings) == 1
    assert findings[0]["tool"] == "pyrefly"
    assert findings[0]["rule_id"] == "bad-assignment"
    assert "bad-assignment" in findings[0]["tool_message"]
    assert Path(findings[0]["filename"]).resolve() == root / "bad.py"
    assert findings[0]["location"]["row"] == 1


def test_clean_file(native_examples: Batch):
    assert json.loads(native_examples[1]["clean.py"]) == []


def test_command_error(run_adapter: RunAdapter):
    result = run_adapter("--nonexistent-option")
    assert result.returncode != 0
    assert result.stdout == ""
    assert result.stderr


@pytest.mark.parametrize(("source", "code"), ANY_EXAMPLES)
def test_any_is_disallowed(native_examples: Batch, source: str, code: str):
    assert code in [f["rule_id"] for f in json.loads(native_examples[1][f"{code}.py"])]


def test_native_selection(native_examples: Batch, run_selected_adapter: RunSelected):
    root, results = native_examples
    assert {f["rule_id"] for f in json.loads(results["mixed.py"])} == {
        "explicit-any",
        "bad-assignment",
    }
    result = run_selected_adapter(root / "mixed.py", ["bad-assignment"])
    assert result.returncode == 0, result.stderr
    assert [f["rule_id"] for f in json.loads(result.stdout)] == ["bad-assignment"]
