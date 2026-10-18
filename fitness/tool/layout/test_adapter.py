import subprocess
from collections.abc import Callable
from pathlib import Path
from types import ModuleType
from typing import cast

import pytest
from pydantic import JsonValue

RunConfiguredAdapter = Callable[[Path, dict[str, JsonValue]], subprocess.CompletedProcess[str]]
Findings = Callable[[Path], list[dict[str, str]]]
TokenFindings = Callable[[Path, int, str], list[dict[str, str]]]
Evaluate = Callable[[Path, dict[str, JsonValue]], list[dict[str, str]]]


@pytest.fixture
def findings(adapter_module: ModuleType) -> Findings:
    def evaluate(root: Path) -> list[dict[str, str]]:
        request = adapter_module.Request.model_validate(
            {
                "selections": [
                    {
                        "rules": [
                            "adapter-test-location",
                            "adapter-folder",
                            "ruff-config-location",
                            "fitness-owns-ruff-check",
                        ]
                    }
                ]
            }
        )
        return adapter_module.findings(root, request)

    return evaluate


@pytest.fixture
def token_findings(adapter_module: ModuleType) -> TokenFindings:
    return cast(TokenFindings, adapter_module.token_findings)


@pytest.fixture
def evaluate(adapter_module: ModuleType) -> Evaluate:
    def run(root: Path, payload: dict[str, JsonValue]) -> list[dict[str, str]]:
        return adapter_module.findings(root, adapter_module.Request.model_validate(payload))

    return run


def test_reports_each_misplaced_adapter_test(tmp_path: Path, findings: Findings):
    tests = tmp_path / "tests" / "nested"
    tests.mkdir(parents=True)
    for name in ("test_adapters.py", "test_ruff_adapter.py", "test_fitness.py"):
        (tests / name).touch()
    result = findings(tmp_path)
    assert [item["filename"] for item in result] == [
        "tests/nested/test_adapters.py",
        "tests/nested/test_ruff_adapter.py",
    ]
    assert all(item["rule_id"] == "adapter-test-location" for item in result)


def test_adapter_tests_in_tool_are_allowed(tmp_path: Path, findings: Findings):
    tool = tmp_path / "fitness" / "tool" / "example"
    tool.mkdir(parents=True)
    (tool / "adapter.py").touch()
    (tool / "test_adapter.py").touch()
    assert findings(tmp_path) == []


@pytest.mark.parametrize(
    "configuration",
    ["[tool.ruff]\n", "[tool.ruff]\nline-length = 100\n", '[tool.ruff.lint]\nselect = ["F"]\n'],
)
def test_rejects_ruff_configuration_in_pyproject(
    tmp_path: Path, configuration: str, findings: Findings
):
    (tmp_path / "pyproject.toml").write_text(configuration)
    result = findings(tmp_path)
    assert len(result) == 1
    assert result[0]["rule_id"] == "ruff-config-location"
    assert result[0]["filename"] == "pyproject.toml"


def test_allows_other_native_configuration(tmp_path: Path, findings: Findings):
    (tmp_path / "pyproject.toml").write_text('[tool.pyrefly]\npython-version = "3.11"\n')
    assert findings(tmp_path) == []


def test_rejects_direct_ruff_checks_in_justfile(tmp_path: Path, findings: Findings):
    (tmp_path / "justfile").write_text("lint:\n    uv run ruff check .\n    ruff check --fix .\n")
    result = findings(tmp_path)
    assert len(result) == 2
    assert all(item["rule_id"] == "fitness-owns-ruff-check" for item in result)
    assert all(item["filename"] == "justfile" for item in result)


def test_allows_fitness_and_formatting_recipes(tmp_path: Path, findings: Findings):
    (tmp_path / "justfile").write_text(
        "# ruff check belongs in the adapter\n"
        "fmt:\n    uv run ruff format .\n"
        "fitness:\n    # Do not run ruff check here\n    .fitness-runner/bin/fitness check\n"
    )
    assert findings(tmp_path) == []


def test_requires_adapter_folder_and_colocated_tests(tmp_path: Path, findings: Findings):
    tool = tmp_path / "fitness" / "tool"
    tool.mkdir(parents=True)
    (tool / "legacy_adapter.py").touch()
    (tool / "test_orphan.py").touch()
    lonely = tool / "lonely"
    lonely.mkdir()
    (lonely / "adapter.py").touch()
    result = findings(tmp_path)
    assert {(item["filename"], item["rule_id"]) for item in result} == {
        ("fitness/tool/test_orphan.py", "adapter-test-location"),
        ("fitness/tool/legacy_adapter.py", "adapter-folder"),
        ("fitness/tool/lonely/adapter.py", "adapter-folder"),
    }


def test_document_filenames_do_not_restrict_function_types(tmp_path: Path, findings: Findings):
    rules = tmp_path / "fitness" / "functions"
    rules.mkdir(parents=True)
    (rules / "architecture.yaml").write_text("""
description: Expectations for a subject spanning several types.
functions:
  - {title: Structure, type: architecture}
  - {title: Quality, type: lint}
  - {title: Typing, type: typing}
""")
    assert findings(tmp_path) == []


def test_combined_token_budget_and_deterministic_file_policy(
    tmp_path: Path, write_file: Callable[[str, str], Path], token_findings: TokenFindings
):
    text = "hello world\r\n<|endoftext|>\n"
    included = [
        "src/fitness/features/orders/contract.py",
        "src/fitness/features/orders/execution.py",
        "src/fitness/features/orders/nested/helpers.py",
    ]
    for name in included:
        write_file(name, text)
    for name in [
        "src/fitness/features/orders/.hidden.txt",
        "src/fitness/features/orders/__pycache__/cached.py",
        "src/fitness/features/orders/image.bin",
        "src/fitness/contracts/shared.py",
        "tests/features/orders/test_orders.py",
        "docs/features/orders/design.md",
        "tests/test_cli.py",
        "tests/conftest.py",
        "tests/fixtures/findings.json",
        "tests/unassociated.txt",
    ]:
        write_file(name, text * 100)
    # Fixed cl100k_base fixture: hello, ' world', CRLF, <, |, endo, ft, ext, |, >LF.
    # Three source files, ten ordinary-text tokens each (including special-token text).
    count = 30
    assert token_findings(tmp_path, count, "cl100k_base") == []
    violations = token_findings(tmp_path, count - 1, "cl100k_base")
    assert len(violations) == 1
    assert f"{count} tokens" in violations[0]["tool_message"]


@pytest.mark.parametrize(
    ("config", "diagnostic"),
    [
        ({"budget": 10, "encoding": "missing"}, "Unknown encoding missing"),
        (
            {"budget": 10, "encoding": "cl100k_base", "associated_files": {"missing": []}},
            "extra_forbidden",
        ),
        ({"budget": 10, "encoding": "cl100k_base", "extra": True}, "extra_forbidden"),
    ],
)
def test_invalid_token_configuration_is_an_error(
    tmp_path: Path,
    write_file: Callable[[str, str], Path],
    config: dict[str, JsonValue],
    diagnostic: str,
    evaluate: Evaluate,
    capsys: pytest.CaptureFixture[str],
):
    write_file("src/fitness/features/orders/contract.py", "")
    with pytest.raises(ValueError, match=diagnostic):
        evaluate(tmp_path, {"selections": [{"rules": ["feature-token-budget"], "config": config}]})
    assert capsys.readouterr().out == ""


def test_unknown_distribution_requires_mapping(
    tmp_path: Path,
    write_file: Callable[[str, str], Path],
    evaluate: Evaluate,
    capsys: pytest.CaptureFixture[str],
):
    write_file("pyproject.toml", '[project]\ndependencies = ["unmapped"]\n')
    with pytest.raises(ValueError, match="No explicit distribution/import mapping"):
        evaluate(
            tmp_path,
            {"selections": [{"rules": ["dependency-placement"], "config": {"module_mapping": {}}}]},
        )
    assert capsys.readouterr().out == ""


@pytest.mark.parametrize(
    ("payload", "diagnostic"),
    [
        ({"config": {"unknown": True}}, "too_long"),
        ({"selections": [{"rules": None}]}, "Layout selections require explicit rule IDs"),
        ({"selections": [{"rules": ["unknown"]}]}, "Unsupported layout rule: unknown"),
        (
            {
                "selections": [
                    {"rules": ["contract-only-feature-access"], "config": {"unknown": True}}
                ]
            },
            "extra_forbidden",
        ),
        (
            {
                "selections": [
                    {
                        "rules": ["feature-token-budget"],
                        "config": {"budget": 100, "encoding": "cl100k_base"},
                    },
                    {
                        "rules": ["feature-token-budget"],
                        "config": {"budget": 200, "encoding": "cl100k_base"},
                    },
                ]
            },
            "Conflicting configuration for feature-token-budget",
        ),
    ],
)
def test_invalid_requests_report_the_intended_error(
    tmp_path: Path,
    evaluate: Evaluate,
    payload: dict[str, JsonValue],
    diagnostic: str,
    capsys: pytest.CaptureFixture[str],
):
    with pytest.raises(ValueError, match=diagnostic):
        evaluate(tmp_path, payload)
    assert capsys.readouterr().out == ""


def test_invalid_request_cli_has_no_partial_output(
    tmp_path: Path, run_configured_adapter: RunConfiguredAdapter
):
    result = run_configured_adapter(tmp_path, {"config": {"unknown": True}})
    assert result.returncode != 0
    assert "too_long" in result.stderr
    assert result.stdout == ""


def test_token_budget_does_not_follow_symlinks(
    tmp_path: Path, write_file: Callable[[str, str], Path], token_findings: TokenFindings
):
    write_file("src/fitness/features/orders/contract.py", "pass")
    external = write_file("external/large.txt", "hello world\n" * 1000)
    (tmp_path / "src/fitness/features/orders/linked.txt").symlink_to(external)
    (tmp_path / "src/fitness/features/orders/linked").symlink_to(
        external.parent, target_is_directory=True
    )
    assert token_findings(tmp_path, 1, "cl100k_base") == []


def test_invalid_python_is_an_evaluation_error(
    tmp_path: Path,
    write_file: Callable[[str, str], Path],
    run_configured_adapter: RunConfiguredAdapter,
):
    write_file("src/broken.py", "def invalid syntax")
    result = run_configured_adapter(
        tmp_path,
        {
            "selections": [
                {"rules": ["contract-only-feature-access"]},
                {"rules": ["dependency-placement"], "config": {"module_mapping": {}}},
            ]
        },
    )
    assert result.returncode != 0
    assert "PartialParsing" in result.stderr
    assert result.stdout == ""
