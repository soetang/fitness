import json
import subprocess
import sys
from pathlib import Path

import pytest


def findings(root: Path) -> list[dict[str, str]]:
    result = subprocess.run(
        [sys.executable, str(Path(__file__).with_name("adapter.py"))],
        cwd=root,
        capture_output=True,
        text=True,
        check=True,
    )
    return json.loads(result.stdout)


def test_reports_each_misplaced_adapter_test(tmp_path: Path):
    tests = tmp_path / "tests" / "nested"
    tests.mkdir(parents=True)
    for name in ("test_adapters.py", "test_ruff_adapter.py", "test_fitness.py"):
        (tests / name).touch()
    result = findings(tmp_path)
    assert [item["filename"] for item in result] == [
        "tests/nested/test_adapters.py",
        "tests/nested/test_ruff_adapter.py",
    ]
    assert all(item["rule_id"] == "adapter-test-location" for item in result)


def test_adapter_tests_in_tool_are_allowed(tmp_path: Path):
    tool = tmp_path / "fitness" / "tool" / "example"
    tool.mkdir(parents=True)
    (tool / "adapter.py").touch()
    (tool / "test_adapter.py").touch()
    assert findings(tmp_path) == []


@pytest.mark.parametrize(
    "configuration",
    ["[tool.ruff]\n", "[tool.ruff]\nline-length = 100\n", '[tool.ruff.lint]\nselect = ["F"]\n'],
)
def test_rejects_ruff_configuration_in_pyproject(tmp_path: Path, configuration: str):
    (tmp_path / "pyproject.toml").write_text(configuration)
    result = findings(tmp_path)
    assert len(result) == 1
    assert result[0]["rule_id"] == "ruff-config-location"
    assert result[0]["filename"] == "pyproject.toml"


def test_allows_other_native_configuration(tmp_path: Path):
    (tmp_path / "pyproject.toml").write_text('[tool.pyrefly]\npython-version = "3.11"\n')
    assert findings(tmp_path) == []


def test_rejects_direct_ruff_checks_in_justfile(tmp_path: Path):
    (tmp_path / "justfile").write_text("lint:\n    uv run ruff check .\n    ruff check --fix .\n")
    result = findings(tmp_path)
    assert len(result) == 2
    assert all(item["rule_id"] == "fitness-owns-ruff-check" for item in result)
    assert all(item["filename"] == "justfile" for item in result)


def test_allows_fitness_and_formatting_recipes(tmp_path: Path):
    (tmp_path / "justfile").write_text(
        "# ruff check belongs in the adapter\n"
        "fmt:\n    uv run ruff format .\n"
        "fitness:\n    # Do not run ruff check here\n    .fitness-runner/bin/fitness check\n"
    )
    assert findings(tmp_path) == []


def test_requires_adapter_folder_and_colocated_tests(tmp_path: Path):
    tool = tmp_path / "fitness" / "tool"
    tool.mkdir(parents=True)
    (tool / "legacy_adapter.py").touch()
    (tool / "test_orphan.py").touch()
    lonely = tool / "lonely"
    lonely.mkdir()
    (lonely / "adapter.py").touch()
    result = findings(tmp_path)
    assert {(item["filename"], item["rule_id"]) for item in result} == {
        ("fitness/tool/test_orphan.py", "adapter-test-location"),
        ("fitness/tool/legacy_adapter.py", "adapter-folder"),
        ("fitness/tool/lonely/adapter.py", "adapter-folder"),
    }


def test_architecture_file_allows_only_architecture_functions(tmp_path: Path):
    rules = tmp_path / "fitness" / "functions"
    rules.mkdir(parents=True)
    (rules / "architecture.yaml").write_text("""
functions:
  - {title: Valid architecture, type: architecture}
  - {title: Misplaced lint, type: lint}
  - {title: Misplaced typing, type: typing}
""")
    result = findings(tmp_path)
    assert len(result) == 2
    assert all(item["rule_id"] == "architecture-function-type" for item in result)
    assert all(item["filename"] == "fitness/functions/architecture.yaml" for item in result)


def test_type_restriction_is_specific_to_architecture_file(tmp_path: Path):
    rules = tmp_path / "fitness" / "functions"
    rules.mkdir(parents=True)
    (rules / "package.yaml").write_text("functions: [{title: Lint, type: lint}]")
    (rules / "architecture.yaml").write_text("functions: [{title: Layout, type: architecture}]")
    assert findings(tmp_path) == []
