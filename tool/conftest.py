import json
import subprocess
import sys
from pathlib import Path

import pytest


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
