from collections.abc import Callable
from pathlib import Path
from types import ModuleType
from typing import cast

import pytest
from pydantic import JsonValue

Evaluate = Callable[[Path, dict[str, JsonValue]], list[dict[str, str]]]
RULES = [
    "adapter-test-location",
    "adapter-folder",
    "ruff-config-location",
    "fitness-owns-ruff-check",
]


@pytest.fixture
def evaluate(adapter_module: ModuleType) -> Evaluate:
    def run(root: Path, payload: dict[str, JsonValue]) -> list[dict[str, str]]:
        return adapter_module.findings(root, adapter_module.Request.model_validate(payload))

    return run


@pytest.mark.parametrize("rules", [[], *[[rule] for rule in RULES], RULES])
def test_selection_controls_all_layout_findings(
    tmp_path: Path,
    write_file: Callable[[str, str], Path],
    evaluate: Evaluate,
    rules: list[str],
):
    write_file("tests/test_example_adapter.py", "")
    write_file("fitness/tool/example/adapter.py", "")
    write_file("pyproject.toml", "[tool.ruff]\n")
    write_file("justfile", "lint:\n    ruff check .\n")
    result = evaluate(tmp_path, {"selections": [{"rules": cast(JsonValue, rules)}]})
    assert sorted(item["rule_id"] for item in result) == sorted(rules)


def test_unselected_checks_do_not_read_malformed_inputs(
    tmp_path: Path,
    write_file: Callable[[str, str], Path],
    evaluate: Evaluate,
):
    write_file("pyproject.toml", "[invalid")
    write_file("src/broken.py", "def invalid syntax")
    result = evaluate(tmp_path, {"selections": [{"rules": ["adapter-test-location"]}]})
    assert result == []


@pytest.mark.parametrize("rule", RULES)
def test_configuration_is_validated_before_analysis(
    tmp_path: Path,
    write_file: Callable[[str, str], Path],
    evaluate: Evaluate,
    rule: str,
    capsys: pytest.CaptureFixture[str],
):
    write_file("src/broken.py", "def invalid syntax")
    with pytest.raises(ValueError, match="extra_forbidden"):
        evaluate(
            tmp_path,
            {
                "selections": [
                    {"rules": ["contract-only-feature-access"]},
                    {"rules": [rule], "config": {"unknown": True}},
                ]
            },
        )
    assert capsys.readouterr().out == ""


def test_duplicate_selections_report_each_finding_once(
    tmp_path: Path,
    write_file: Callable[[str, str], Path],
    evaluate: Evaluate,
):
    write_file("justfile", "lint:\n    ruff check .\n")
    result = evaluate(
        tmp_path,
        {"selections": [{"rules": ["fitness-owns-ruff-check"]}] * 2},
    )
    assert [item["rule_id"] for item in result] == ["fitness-owns-ruff-check"]


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
