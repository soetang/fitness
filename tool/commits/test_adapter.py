import json
import subprocess
from collections.abc import Callable
from pathlib import Path

import pytest

RunAdapter = Callable[[str | Path], subprocess.CompletedProcess[str]]


def git(root: Path, *args: str) -> None:
    subprocess.run(["git", "-C", str(root), *args], check=True, capture_output=True)


@pytest.fixture
def repository(tmp_path: Path) -> Path:
    git(tmp_path, "init")
    return tmp_path


def stage(root: Path, paths: list[str]) -> None:
    for name in paths:
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("example\n")
        git(root, "add", "--", name)


@pytest.mark.parametrize(
    "paths",
    [
        [],
        ["fitnessfunctions/example.yaml", "tool/example/adapter.py"],
        ["src/example.py", "tests/test_example.py"],
        ["README.md", "pyproject.toml"],
        ["fitnessfunctions/example.yaml", "README.md"],
    ],
)
def test_allowed_commit_groups(repository: Path, run_adapter: RunAdapter, paths: list[str]):
    stage(repository, paths)
    result = run_adapter(repository)
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout) == []


@pytest.mark.parametrize("definition", ["fitnessfunctions/example.yaml", "tool/example/adapter.py"])
@pytest.mark.parametrize("implementation", ["src/example.py", "tests/test_example.py"])
def test_rejects_every_mixed_pair(
    repository: Path, run_adapter: RunAdapter, definition: str, implementation: str
):
    stage(repository, [definition, implementation])
    result = run_adapter(repository)
    assert result.returncode == 0, result.stderr
    findings = json.loads(result.stdout)
    assert len(findings) == 1
    assert findings[0]["rule_id"] == "separate-definition-and-implementation-changes"
    assert definition in findings[0]["tool_message"]
    assert implementation in findings[0]["tool_message"]


def test_unstaged_changes_do_not_affect_commit(repository: Path, run_adapter: RunAdapter):
    stage(repository, ["fitnessfunctions/example.yaml"])
    source = repository / "src" / "example.py"
    source.parent.mkdir()
    source.write_text("unstaged\n")
    assert json.loads(run_adapter(repository).stdout) == []


def test_non_repository_is_an_execution_error(tmp_path: Path, run_adapter: RunAdapter):
    result = run_adapter(tmp_path)
    assert result.returncode != 0
    assert result.stdout == ""
