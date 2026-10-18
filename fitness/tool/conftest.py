import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest
from pydantic import JsonValue


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
