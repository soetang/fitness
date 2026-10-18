import json
import sys
from collections.abc import Callable
from pathlib import Path

import pytest
from typer.testing import CliRunner

from fitness.cli import create_app
from fitness.core import FitnessError, Suite, evaluate, load, run_command


def test_shared_counts_limits_and_source(suite: Suite, findings_json: str):
    requests = []

    def runner(command: list[str], stdin: str | None):
        assert stdin is not None
        requests.append((command, json.loads(stdin)))
        return findings_json

    results = evaluate(suite, runner)
    assert [r.status for r in results] == ["FAIL", "PASS", "NOT AUTOMATED"]
    assert [len(r.findings) for r in results] == [1, 1, 0]
    assert results[0].definition.source.endswith("apis.yaml:2")
    assert len(requests) == 1
    assert requests[0][1] == {
        "config": {"preview": True},
        "selections": [
            {"rules": ["API001"], "config": {}},
            {"rules": ["API001"], "config": {}},
        ],
    }
    assert len(suite.warnings) == 1


def test_filter_and_empty_findings(suite: Suite):
    def runner(command: list[str], stdin: str | None):
        assert stdin is not None
        assert len(json.loads(stdin)["selections"]) == 1
        return "[]"

    results = evaluate(suite, runner, "migration")
    assert [r.status for r in results] == ["PASS"]


def test_disabled_input(suite: Suite):
    suite.tools["example"].send_input = False

    def runner(command: list[str], stdin: str | None):
        assert stdin is None
        return "[]"

    assert evaluate(suite, runner)[0].status == "PASS"


@pytest.mark.parametrize(
    "text",
    [
        "functions: [{title: Test, type: custom, typo: true}]",
        "functions: [{title: Test, type: custom, limit: -1}]",
        "functions: [{title: Test, type: custom, limit: true}]",
        "functions: [{title: Test, type: custom, tool: missing, rules: [X]}]",
        "functions: [{title: Test, type: custom, rules: [X]}]",
        "functions: [{title: Test, type: custom, tool: example}]",
        "functions: [{title: Test, type: custom, tool: example, rules: []}]",
        "functions: [{title: Test, title: Duplicate, type: custom}]",
        "functions: [{title: Test, type: custom, tool: example, rules: [X, X]}]",
        "? [invalid, key]\n: value",
        "tools: {example: {command: [example], config: {date: 2026-10-18}}}",
        "functions: [",
        "",
    ],
)
def test_invalid_definitions(write_definitions: Callable[[str], Path], text: str):
    with pytest.raises(FitnessError):
        load(write_definitions(text))


def test_duplicate_tools(tmp_path: Path):
    for name in ["a.yaml", "b.yaml"]:
        (tmp_path / name).write_text("tools: {example: {command: [example]}}")
    with pytest.raises(FitnessError, match="duplicate tool"):
        load(tmp_path)


@pytest.mark.parametrize(
    "output",
    [
        "not JSON",
        "{}",
        '[{"tool":"other", "rule_id":"X", "tool_message":"bad"}]',
        '[{"tool":"example", "rule_id":"X"}]',
    ],
)
def test_invalid_tool_output(suite: Suite, output: str):
    with pytest.raises(FitnessError, match="tool 'example'"):
        evaluate(suite, lambda command, stdin: output)


def test_lint_is_offline(definitions_path: Path):
    def forbidden_runner(command: list[str], stdin: str | None):
        pytest.fail("lint must never execute a tool")

    result = CliRunner().invoke(
        create_app(forbidden_runner), ["lint", "--rules", str(definitions_path), "--verbose"]
    )
    assert result.exit_code == 0
    assert "3 functions" in result.output
    assert "WARNING" in result.output


def test_check_presentation(definitions_path: Path, findings_json: str):
    app = create_app(lambda command, stdin: findings_json)
    result = CliRunner().invoke(app, ["check", "--rules", str(definitions_path)])
    assert result.exit_code == 1
    assert "FAIL  Use supported APIs" in result.output
    assert "Guidance:" in result.output
    assert "src/orders/client.py:12:5" in result.output
    assert "NOT AUTOMATED" in result.output
    passed = CliRunner().invoke(
        app, ["check", "--rules", str(definitions_path), "--type", "migration"]
    )
    assert passed.exit_code == 0


def test_execution_error_exit(definitions_path: Path):
    def failing_runner(command: list[str], stdin: str | None):
        raise FitnessError("integration failed")

    result = CliRunner().invoke(
        create_app(failing_runner), ["check", "--rules", str(definitions_path)]
    )
    assert result.exit_code == 2
    assert "ERROR" in result.output
    assert "PASS" not in result.output


def test_real_subprocess(suite: Suite):
    tool = suite.tools["example"]
    tool.command = [sys.executable, "tests/fixtures/report.py"]
    assert evaluate(suite, run_command)[0].status == "FAIL"


def test_process_failure_is_not_a_violation():
    with pytest.raises(FitnessError, match="exit 1"):
        run_command([sys.executable, "-c", "raise SystemExit(1)"], None)


def test_process_without_input():
    assert run_command([sys.executable, "-c", "print('[]')"], None).strip() == "[]"


def test_empty_directory(tmp_path: Path):
    with pytest.raises(FitnessError, match="no YAML definitions found"):
        load(tmp_path)


def test_missing_executable(tmp_path: Path):
    with pytest.raises(FitnessError, match="No such file"):
        run_command([str(tmp_path / "nonexistent-command")], None)


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
    assert result.output == "No matching fitness functions\n"


def test_findings_without_optional_location(definitions_path: Path):
    def runner(command: list[str], stdin: str | None):
        return json.dumps(
            [{"tool": "example", "rule_id": "API001", "tool_message": "Use public APIs."}]
        )

    result = CliRunner().invoke(create_app(runner), ["check", "--rules", str(definitions_path)])
    assert result.exit_code == 1
    assert "example / API001\nUse public APIs." in result.output
    assert "None" not in result.output


def test_omitted_rules_count_all_and_warn_on_overlap(
    write_definitions: Callable[[str], Path], findings_json: str
):
    suite = load(
        write_definitions("""
tools:
  example: {command: [example], send_input: true}
functions:
  - {title: All diagnostics, type: test, tool: example}
  - {title: Specific diagnostic, type: test, tool: example, rules: [API001]}
""")
    )

    def runner(command: list[str], stdin: str | None):
        assert stdin is not None
        assert json.loads(stdin)["selections"][0]["rules"] is None
        return findings_json

    assert len(suite.warnings) == 1
    assert [r.status for r in evaluate(suite, runner)] == ["FAIL", "FAIL"]


@pytest.mark.parametrize(
    ("matching", "first", "second", "counts", "warning_count"),
    [
        ("prefix", "[F]", "[F401]", [1, 1], 1),
        ("prefix", "[F401]", "[F]", [1, 1], 1),
        ("prefix", "[E]", "[F401]", [0, 1], 0),
        ("exact", "[F]", "[F401]", [0, 1], 0),
        ("prefix", "[F, F401]", "[E]", [1, 0], 0),
        ("prefix", "[F]", "null", [1, 1], 1),
        ("prefix", "null", "null", [1, 1], 1),
    ],
)
def test_rule_selector_matching(
    write_definitions: Callable[[str], Path],
    matching: str,
    first: str,
    second: str,
    counts: list[int],
    warning_count: int,
):
    suite = load(
        write_definitions(f"""
tools:
  example: {{command: [example], rule_matching: {matching}}}
functions:
  - {{title: First, type: test, tool: example, rules: {first}}}
  - {{title: Second, type: test, tool: example, rules: {second}}}
""")
    )
    output = '[{"tool":"example", "rule_id":"F401", "tool_message":"Unused import"}]'
    results = evaluate(suite, lambda command, stdin: output)
    assert [len(result.findings) for result in results] == counts
    assert len(suite.warnings) == warning_count
