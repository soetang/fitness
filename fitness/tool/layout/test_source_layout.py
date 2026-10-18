import json
import subprocess
from collections.abc import Callable
from pathlib import Path

from pydantic import JsonValue

RunConfiguredAdapter = Callable[[Path, dict[str, JsonValue]], subprocess.CompletedProcess[str]]


def test_file_length_boundaries_and_scope(
    tmp_path: Path,
    write_file: Callable[[str, str], Path],
    run_configured_adapter: RunConfiguredAdapter,
):
    write_file("src/exact.py", "# line\n" * 400)
    write_file("tests/over_test.py", "# line\n" * 400 + "\n")
    write_file("src/empty.py", "")
    write_file("tests/no_final_newline.py", "\n" * 399 + "pass")
    write_file("fitness/tool/large.py", "# line\n" * 401)
    result = run_configured_adapter(
        tmp_path,
        {
            "selections": [
                {
                    "rules": ["source-test-file-length"],
                    "config": {"max_lines": 400},
                }
            ]
        },
    )
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout) == [
        {
            "tool": "layout",
            "rule_id": "source-test-file-length",
            "tool_message": "401 lines exceeds 400.",
            "filename": "tests/over_test.py",
        }
    ]


def test_feature_test_placement_and_contract_checks_share_analysis(
    tmp_path: Path,
    write_file: Callable[[str, str], Path],
    run_configured_adapter: RunConfiguredAdapter,
):
    contract = "from fitness.features.orders.contract import get_order\n"
    for path in [
        "tests/features/orders/test_contract.py",
        "tests/test_orders.py",
        "tests/features/client/orders_test.py",
        "tests/conftest.py",
    ]:
        write_file(path, contract)
    write_file("tests/test_cli.py", "from fitness.cli import create_app\n")
    write_file(
        "tests/features/orders/test_private.py",
        "from fitness.features.orders.execution import execute\n",
    )
    result = run_configured_adapter(
        tmp_path,
        {
            "selections": [
                {
                    "rules": ["feature-test-location", "contract-only-feature-access"],
                }
            ]
        },
    )
    assert result.returncode == 0, result.stderr
    assert {(f["filename"], f["rule_id"]) for f in json.loads(result.stdout)} == {
        ("tests/test_orders.py", "feature-test-location"),
        ("tests/features/client/orders_test.py", "feature-test-location"),
        ("tests/features/orders/test_private.py", "contract-only-feature-access"),
    }


def test_placement_check_can_run_on_its_own(
    tmp_path: Path,
    write_file: Callable[[str, str], Path],
    run_configured_adapter: RunConfiguredAdapter,
):
    write_file("tests/test_orders.py", "from fitness.features.orders.contract import get_order\n")
    result = run_configured_adapter(
        tmp_path, {"selections": [{"rules": ["feature-test-location"]}]}
    )
    assert result.returncode == 0, result.stderr
    violations = json.loads(result.stdout)
    assert len(violations) == 1
    assert violations[0]["rule_id"] == "feature-test-location"
    assert "tests/features/orders/" in violations[0]["tool_message"]
