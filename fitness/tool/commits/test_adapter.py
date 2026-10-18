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
        ["fitness/functions/example.yaml", "fitness/tool/example/adapter.py"],
        ["src/example.py", "tests/test_example.py"],
        ["README.md", "pyproject.toml"],
        ["fitness/functions/example.yaml", "README.md"],
        [
            "src/fitness/features/orders/contract.py",
            "tests/features/orders/test_orders.py",
            "docs/features/orders/design.md",
            "src/fitness/contracts/domain.py",
        ],
    ],
)
def test_allowed_commit_groups(repository: Path, run_adapter: RunAdapter, paths: list[str]):
    stage(repository, paths)
    result = run_adapter(repository)
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout) == []


@pytest.mark.parametrize(
    "definition",
    ["fitness/functions/example.yaml", "fitness/tool/example/adapter.py", "fitness/tool.yaml"],
)
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
    stage(repository, ["fitness/functions/example.yaml"])
    source = repository / "src" / "example.py"
    source.parent.mkdir()
    source.write_text("unstaged\n")
    assert json.loads(run_adapter(repository).stdout) == []


def test_non_repository_is_an_execution_error(tmp_path: Path, run_adapter: RunAdapter):
    result = run_adapter(tmp_path)
    assert result.returncode != 0
    assert result.stdout == ""


@pytest.mark.parametrize(
    "second",
    [
        "src/fitness/features/client/contract.py",
        "tests/features/client/test_client.py",
        "docs/features/client/design.md",
    ],
)
def test_rejects_multiple_staged_features(repository: Path, run_adapter: RunAdapter, second: str):
    stage(repository, ["src/fitness/features/orders/contract.py", second])
    result = run_adapter(repository)
    assert result.returncode == 0, result.stderr
    violations = json.loads(result.stdout)
    assert len(violations) == 1
    assert violations[0]["rule_id"] == "one-feature-per-commit"


@pytest.mark.parametrize("rename", [False, True])
def test_deletions_and_cross_feature_renames(
    repository: Path, run_adapter: RunAdapter, rename: bool
):
    original = "src/fitness/features/orders/contract.py"
    stage(repository, [original])
    git(
        repository,
        "-c",
        "user.name=Test",
        "-c",
        "user.email=test@example.com",
        "commit",
        "-m",
        "Initial feature",
    )
    target = "src/fitness/features/client/contract.py"
    if rename:
        (repository / target).parent.mkdir(parents=True)
        git(repository, "mv", original, target)
    else:
        git(repository, "rm", original)
        stage(repository, [target])
    result = run_adapter(repository)
    assert result.returncode == 0, result.stderr
    assert [f["rule_id"] for f in json.loads(result.stdout)] == ["one-feature-per-commit"]


def test_unstaged_second_feature_is_ignored(repository: Path, run_adapter: RunAdapter):
    stage(repository, ["src/fitness/features/orders/contract.py"])
    path = repository / "src/fitness/features/client/contract.py"
    path.parent.mkdir(parents=True)
    path.write_text("unstaged\n")
    assert json.loads(run_adapter(repository).stdout) == []


def test_same_feature_rename_is_allowed(repository: Path, run_adapter: RunAdapter):
    original = "src/fitness/features/orders/old.py"
    stage(repository, [original])
    git(
        repository,
        "-c",
        "user.name=Test",
        "-c",
        "user.email=test@example.com",
        "commit",
        "-m",
        "Initial feature",
    )
    git(repository, "mv", original, "src/fitness/features/orders/new.py")
    assert json.loads(run_adapter(repository).stdout) == []
