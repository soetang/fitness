import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest
from pydantic import JsonValue


@pytest.fixture
def write_file(tmp_path: Path):
    def write(name: str, text: str = "") -> Path:
        path = tmp_path / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        return path

    return write


@pytest.fixture(scope="module")
def adapter_module(request: pytest.FixtureRequest):
    """Load the real adapter API for tests that do not need a process boundary."""
    directory = request.path.parent
    spec = importlib.util.spec_from_file_location(
        f"fitness_adapter_{directory.name}", directory / "adapter.py"
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.path.insert(0, str(directory))
    try:
        spec.loader.exec_module(module)
    finally:
        sys.path.pop(0)
    return module


@pytest.fixture
def run_adapter(request: pytest.FixtureRequest):
    def run(*args: str | Path):
        return subprocess.run(
            [sys.executable, str(request.path.parent / "adapter.py"), *map(str, args)],
            capture_output=True,
            text=True,
            input=json.dumps({"config": {}, "selections": [{"rules": None, "config": {}}]}),
            check=False,
        )

    return run


@pytest.fixture(scope="module")
def run_adapter_batch(request: pytest.FixtureRequest, tmp_path_factory: pytest.TempPathFactory):
    """Run compatible examples together, retaining every file's native findings."""

    def run(examples: dict[str, str], payload: dict[str, JsonValue]):
        root = tmp_path_factory.mktemp(request.path.parent.name)
        for name, source in examples.items():
            (root / name).write_text(source)
        result = subprocess.run(
            [sys.executable, str(request.path.parent / "adapter.py"), str(root)],
            input=json.dumps(payload),
            capture_output=True,
            text=True,
            check=False,
        )
        assert result.returncode == 0, result.stderr
        findings = json.loads(result.stdout)
        by_file = {
            name: [item for item in findings if Path(item["filename"]).resolve() == root / name]
            for name in examples
        }
        assert sum(map(len, by_file.values())) == len(findings)
        return root, by_file

    return run


@pytest.fixture
def run_selected_adapter(request: pytest.FixtureRequest):
    def run(path: Path, rules: list[str] | None):
        return subprocess.run(
            [sys.executable, str(request.path.parent / "adapter.py"), str(path)],
            input=json.dumps({"config": {}, "selections": [{"rules": rules, "config": {}}]}),
            capture_output=True,
            text=True,
            check=False,
        )

    return run


@pytest.fixture
def run_configured_adapter(request: pytest.FixtureRequest):
    def run(path: Path, payload: dict[str, JsonValue]):
        return subprocess.run(
            [sys.executable, str(request.path.parent / "adapter.py"), str(path)],
            input=json.dumps(payload),
            capture_output=True,
            text=True,
            check=False,
        )

    return run
