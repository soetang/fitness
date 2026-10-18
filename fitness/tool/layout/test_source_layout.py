import json
import subprocess
from collections.abc import Callable
from pathlib import Path
from types import ModuleType

from pydantic import JsonValue


def test_file_length_boundaries_and_scope(
    tmp_path: Path,
    write_file: Callable[[str, str], Path],
    adapter_module: ModuleType,
):
    write_file("src/exact.py", "# line\n" * 400)
    write_file("tests/over_test.py", "# line\n" * 400 + "\n")
    write_file("src/empty.py", "")
    write_file("tests/no_final_newline.py", "\n" * 399 + "pass")
    write_file("fitness/tool/large.py", "# line\n" * 401)
    result = adapter_module.findings(
        tmp_path,
        adapter_module.Request.model_validate(
            {
                "selections": [
                    {
                        "rules": ["source-test-file-length"],
                        "config": {"max_lines": 400},
                    }
                ]
            }
        ),
    )
    assert result == [
        {
            "tool": "layout",
            "rule_id": "source-test-file-length",
            "tool_message": "401 lines exceeds 400.",
            "filename": "tests/over_test.py",
        }
    ]


def test_dependency_source_scope_ignores_invalid_non_source(
    tmp_path: Path,
    write_file: Callable[[str, str], Path],
    run_configured_adapter: Callable[
        [Path, dict[str, JsonValue]], subprocess.CompletedProcess[str]
    ],
):
    write_file("src/example.py", "import yaml\n")
    write_file("tests/broken.py", "def invalid syntax")
    write_file("pyproject.toml", '[project]\ndependencies = ["PyYAML"]\n')
    result = run_configured_adapter(
        tmp_path,
        {
            "selections": [
                {
                    "rules": ["dependency-placement"],
                    "config": {"module_mapping": {"pyyaml": ["yaml"]}},
                }
            ]
        },
    )
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout) == []
