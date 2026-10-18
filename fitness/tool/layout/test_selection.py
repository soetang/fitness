import json
import subprocess
from collections.abc import Callable
from pathlib import Path
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
    "additional_rules",
    [
        [],
        ["contract-only-feature-access"],
        ["feature-test-location"],
        ["contract-only-feature-access", "feature-test-location"],
    ],
)
def test_selected_rules_determine_shared_import_scope(
    tmp_path: Path,
    write_file: Callable[[str, str], Path],
    run_configured_adapter: RunAdapter,
    additional_rules: list[str],
):
    write_file("src/example.py", "import os\n")
    write_file("tests/test_broken.py", "def invalid syntax")
    selections: list[JsonValue] = [
        {"rules": ["dependency-placement"], "config": {"module_mapping": {}}},
        *[{"rules": cast(JsonValue, [rule])} for rule in additional_rules],
    ]
    result = run_configured_adapter(tmp_path, {"selections": selections})
    if additional_rules:
        assert result.returncode != 0
        assert result.stdout == ""
    else:
        assert result.returncode == 0, result.stderr
        assert json.loads(result.stdout) == []
