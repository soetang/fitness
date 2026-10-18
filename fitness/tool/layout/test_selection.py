import json
import subprocess
from collections.abc import Callable
from pathlib import Path
from types import ModuleType
from typing import cast

import pytest
from pydantic import JsonValue

RunAdapter = Callable[[Path, dict[str, JsonValue]], subprocess.CompletedProcess[str]]
RULES = [
    "adapter-test-location",
    "adapter-folder",
    "ruff-config-location",
    "fitness-owns-ruff-check",
]


@pytest.mark.parametrize("rules", [[], *[[rule] for rule in RULES], RULES])
def test_selection_controls_all_layout_findings(
    tmp_path: Path,
    write_file: Callable[[str, str], Path],
    run_configured_adapter: RunAdapter,
    rules: list[str],
):
    write_file("tests/test_example_adapter.py", "")
    write_file("fitness/tool/example/adapter.py", "")
    write_file("pyproject.toml", "[tool.ruff]\n")
    write_file("justfile", "lint:\n    ruff check .\n")
    result = run_configured_adapter(tmp_path, {"selections": [{"rules": cast(JsonValue, rules)}]})
    assert result.returncode == 0, result.stderr
    assert sorted(item["rule_id"] for item in json.loads(result.stdout)) == sorted(rules)


def test_unselected_checks_do_not_read_malformed_inputs(
    tmp_path: Path,
    write_file: Callable[[str, str], Path],
    run_configured_adapter: RunAdapter,
):
    write_file("pyproject.toml", "[invalid")
    write_file("src/broken.py", "def invalid syntax")
    result = run_configured_adapter(
        tmp_path, {"selections": [{"rules": ["adapter-test-location"]}]}
    )
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout) == []


@pytest.mark.parametrize("rule", RULES)
def test_configuration_is_validated_before_analysis(
    tmp_path: Path,
    write_file: Callable[[str, str], Path],
    run_configured_adapter: RunAdapter,
    rule: str,
):
    write_file("src/broken.py", "def invalid syntax")
    result = run_configured_adapter(
        tmp_path,
        {
            "selections": [
                {"rules": ["contract-only-feature-access"]},
                {"rules": [rule], "config": {"unknown": True}},
            ]
        },
    )
    assert result.returncode != 0
    assert "extra_forbidden" in result.stderr
    assert result.stdout == ""


def test_duplicate_selections_report_each_finding_once(
    tmp_path: Path,
    write_file: Callable[[str, str], Path],
    run_configured_adapter: RunAdapter,
):
    write_file("justfile", "lint:\n    ruff check .\n")
    result = run_configured_adapter(
        tmp_path,
        {"selections": [{"rules": ["fitness-owns-ruff-check"]}] * 2},
    )
    assert result.returncode == 0, result.stderr
    assert [item["rule_id"] for item in json.loads(result.stdout)] == ["fitness-owns-ruff-check"]


@pytest.mark.parametrize(
    ("rules", "expected_scopes"),
    [
        ([], []),
        (["adapter-test-location"], []),
        (["dependency-placement"], [True]),
        (["contract-only-feature-access"], [False]),
        (["feature-test-location"], [False]),
        (["dependency-placement", "contract-only-feature-access"], [False]),
        (["dependency-placement", "feature-test-location"], [False]),
        (
            ["dependency-placement", "contract-only-feature-access", "feature-test-location"],
            [False],
        ),
    ],
)
def test_selected_rules_determine_shared_import_scope(
    tmp_path: Path,
    adapter_module: ModuleType,
    rules: list[str],
    expected_scopes: list[bool],
):
    calls: list[tuple[Path, bool]] = []

    def scan(root: Path, source_only: bool) -> dict[Path, list[tuple[str, int]]]:
        calls.append((root, source_only))
        return {}

    request = adapter_module.Request.model_validate(
        {
            "selections": [
                {
                    "rules": [rule],
                    "config": {"module_mapping": {}} if rule == "dependency-placement" else {},
                }
                for rule in rules
            ]
        }
    )
    assert adapter_module.findings(tmp_path, request, scanner=scan) == []
    assert calls == [(tmp_path.resolve(), scope) for scope in expected_scopes]


def test_combined_rules_evaluate_the_shared_inventory(tmp_path: Path, adapter_module: ModuleType):
    inventory = {
        tmp_path / "src/client.py": [("fitness.features.orders.execution", 1)],
        tmp_path / "tests/test_orders.py": [("fitness.features.orders.contract", 1)],
    }
    calls: list[tuple[Path, bool]] = []

    def scan(root: Path, source_only: bool) -> dict[Path, list[tuple[str, int]]]:
        calls.append((root, source_only))
        return inventory

    request = adapter_module.Request.model_validate(
        {"selections": [{"rules": ["contract-only-feature-access", "feature-test-location"]}]}
    )
    results = adapter_module.findings(tmp_path, request, scanner=scan)
    assert calls == [(tmp_path.resolve(), False)]
    assert [(item["rule_id"], item["filename"]) for item in results] == [
        ("contract-only-feature-access", "src/client.py"),
        ("feature-test-location", "tests/test_orders.py"),
    ]
