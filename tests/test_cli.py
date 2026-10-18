import json
from collections.abc import Callable
from pathlib import Path

import pytest
from typer.testing import CliRunner

from fitness.cli import create_app
from fitness.contracts import FitnessError


def test_lint_is_offline(definitions_path: Path):
    def forbidden_runner(command: list[str], stdin: str | None):
        pytest.fail("lint must never execute a tool")

    result = CliRunner().invoke(
        create_app(forbidden_runner), ["lint", "--rules", str(definitions_path), "--verbose"]
    )
    assert result.exit_code == 0
    assert "3 functions" in result.output
    assert "WARNING" in result.output


def test_check_presents_failures(definitions_path: Path, findings_json: str):
    app = create_app(lambda command, stdin: findings_json)
    result = CliRunner().invoke(app, ["check", "--rules", str(definitions_path)])
    assert result.exit_code == 1
    assert "FAIL  Use supported APIs" in result.output
    assert "Guidance:" in result.output
    assert "src/orders/client.py:12:5" in result.output


def test_check_omits_successful_functions(definitions_path: Path, findings_json: str):
    app = create_app(lambda command, stdin: findings_json)
    result = CliRunner().invoke(app, ["check", "--rules", str(definitions_path)])
    assert result.exit_code == 1
    assert "NOT AUTOMATED" not in result.output
    assert "PASS" not in result.output
    assert "Keep API migration within budget" not in result.output
    assert "Keep features independent" not in result.output
    assert "success" not in result.output


def test_filtered_check_reports_success(definitions_path: Path, findings_json: str):
    app = create_app(lambda command, stdin: findings_json)
    passed = CliRunner().invoke(
        app, ["check", "--rules", str(definitions_path), "--type", "migration"]
    )
    assert passed.exit_code == 0
    assert passed.output == "success\n"


def test_execution_error_exit(definitions_path: Path):
    def failing_runner(command: list[str], stdin: str | None):
        raise FitnessError("integration failed")

    result = CliRunner().invoke(
        create_app(failing_runner), ["check", "--rules", str(definitions_path)]
    )
    assert result.exit_code == 2
    assert "ERROR" in result.output
    assert "PASS" not in result.output


def test_lint_error_exit(write_definitions: Callable[[str], Path]):
    path = write_definitions("functions: [{title: Missing type}]")
    result = CliRunner().invoke(create_app(), ["lint", "--rules", str(path)])
    assert result.exit_code == 2
    assert "ERROR" in result.output
    assert "Valid fitness definitions" not in result.output


def test_lint_without_verbose_or_warnings(write_definitions: Callable[[str], Path]):
    path = write_definitions("functions: [{title: Review interfaces, type: architecture}]")
    result = CliRunner().invoke(create_app(), ["lint", "--rules", str(path)])
    assert result.exit_code == 0
    assert result.output == "Valid fitness definitions\n"


def test_no_matching_functions_skips_tools(definitions_path: Path):
    def forbidden_runner(command: list[str], stdin: str | None):
        pytest.fail("unselected tools must not execute")

    result = CliRunner().invoke(
        create_app(forbidden_runner),
        ["check", "--rules", str(definitions_path), "--type", "unknown"],
    )
    assert result.exit_code == 0
    assert result.output == "success\n"


def test_findings_without_optional_location(definitions_path: Path):
    def runner(command: list[str], stdin: str | None):
        return json.dumps(
            [{"tool": "example", "rule_id": "API001", "tool_message": "Use public APIs."}]
        )

    result = CliRunner().invoke(create_app(runner), ["check", "--rules", str(definitions_path)])
    assert result.exit_code == 1
    assert "example / API001\nUse public APIs." in result.output
    assert "None" not in result.output


def test_failure_without_guidance(write_definitions: Callable[[str], Path], findings_json: str):
    path = write_definitions("""
tools:
  example: {command: [example]}
functions:
  - {title: No violations, type: test, tool: example, rules: [API001]}
""")
    result = CliRunner().invoke(
        create_app(lambda command, stdin: findings_json), ["check", "--rules", str(path)]
    )
    assert result.exit_code == 1
    assert "FAIL  No violations" in result.output
    assert "Guidance:" not in result.output


def test_nonautomated_functions_are_silent(write_definitions: Callable[[str], Path]):
    path = write_definitions("functions: [{title: Review manually, type: architecture}]")

    def forbidden_runner(command: list[str], stdin: str | None):
        pytest.fail("nonautomated functions must not execute tools")

    result = CliRunner().invoke(create_app(forbidden_runner), ["check", "--rules", str(path)])
    assert result.exit_code == 0
    assert result.output == "success\n"
