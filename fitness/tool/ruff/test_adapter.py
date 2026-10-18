import json
import subprocess
from collections.abc import Callable
from pathlib import Path
from subprocess import CompletedProcess
from types import ModuleType

import pytest
from pydantic import JsonValue

RunAdapter = Callable[[str | Path], CompletedProcess[str]]
RunSelected = Callable[[Path, list[str] | None], CompletedProcess[str]]
RunConfigured = Callable[[Path, dict[str, JsonValue]], CompletedProcess[str]]
Batch = tuple[Path, dict[str, list[dict[str, JsonValue]]]]
RunBatch = Callable[[dict[str, str], dict[str, JsonValue]], Batch]

pytestmark = pytest.mark.xdist_group("ruff_native_examples")

BANNED_EXAMPLES = [
    "import dataclasses\n",
    "from dataclasses import dataclass\n",
    "from pydantic.dataclasses import dataclass\n",
    "from pydantic import dataclasses\n",
]
SUPPRESSION_EXAMPLES: list[tuple[str, list[str]]] = [
    ("# noqa", ["PGH004"]),
    ("# noqa: F401", []),
    ("# ruff: noqa", ["PGH004"]),
]


@pytest.fixture(scope="module")
def default_examples(run_adapter_batch: RunBatch) -> Batch:
    return run_adapter_batch(
        {"bad.py": "import os\n", "clean.py": "value: int = 1\n"},
        {"config": {}, "selections": [{"rules": None, "config": {}}]},
    )


@pytest.fixture(scope="module")
def suppression_examples(run_adapter_batch: RunBatch) -> Batch:
    return run_adapter_batch(
        {
            f"{index}.py": (
                f"{comment}\nimport os\n" if "ruff:" in comment else f"import os  {comment}\n"
            )
            for index, (comment, _) in enumerate(SUPPRESSION_EXAMPLES)
        },
        {"config": {}, "selections": [{"rules": ["PGH004"], "config": {}}]},
    )


@pytest.fixture(scope="module")
def banned_examples(run_adapter_batch: RunBatch) -> Batch:
    return run_adapter_batch(
        {f"{index}.py": source for index, source in enumerate(BANNED_EXAMPLES)},
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


@pytest.fixture(scope="module")
def prefix_diagnostics(tmp_path_factory: pytest.TempPathFactory, adapter_module: ModuleType):
    """Scan once; selector attribution is adapter policy, not a new native scan."""
    path = tmp_path_factory.mktemp("ruff-selectors") / "example.py"
    path.write_text("import os\n")
    selectors = ["F", "F4", "F401"]
    result = subprocess.run(
        [
            "ruff",
            "check",
            "--output-format",
            "json",
            *adapter_module._selection_flags(selectors, [selectors]),
            str(path),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 1, result.stderr
    assert [item["code"] for item in json.loads(result.stdout)] == ["F401"]
    return result


def test_reports_offender(default_examples: Batch):
    root, results = default_examples
    findings = results["bad.py"]
    assert len(findings) == 1
    assert findings[0]["tool"] == "ruff"
    assert findings[0]["rule_id"] == "F401"
    message, filename, location = (
        findings[0]["tool_message"],
        findings[0]["filename"],
        findings[0]["location"],
    )
    assert isinstance(message, str) and "F401" in message
    assert isinstance(filename, str) and Path(filename).resolve() == root / "bad.py"
    assert isinstance(location, dict) and location["row"] == 1


def test_clean_file(default_examples: Batch):
    assert default_examples[1]["clean.py"] == []


def test_command_error(run_adapter: RunAdapter):
    result = run_adapter("--nonexistent-option")
    assert result.returncode != 0
    assert result.stdout == ""
    assert result.stderr


@pytest.mark.parametrize(
    ("index", "expected"),
    [(index, expected) for index, (_, expected) in enumerate(SUPPRESSION_EXAMPLES)],
    ids=[comment for comment, _ in SUPPRESSION_EXAMPLES],
)
def test_blanket_suppressions_only(suppression_examples: Batch, index: int, expected: list[str]):
    assert [f["rule_id"] for f in suppression_examples[1][f"{index}.py"]] == expected


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
    adapter_module: ModuleType,
    prefix_diagnostics: CompletedProcess[str],
    selectors: list[str],
    expected: str,
):
    assert adapter_module._selection_flags(selectors, [selectors]) == [
        "--select",
        ",".join(selectors),
    ]
    findings = adapter_module._normalize_findings(prefix_diagnostics, selectors)
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
    "index",
    range(len(BANNED_EXAMPLES)),
    ids=BANNED_EXAMPLES,
)
def test_banned_api_configuration(banned_examples: Batch, index: int):
    findings = banned_examples[1][f"{index}.py"]
    assert len(findings) == 1
    assert findings[0]["rule_id"] == "TID251"
    message = findings[0]["tool_message"]
    assert isinstance(message, str) and "Use Pydantic BaseModel." in message


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
