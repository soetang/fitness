import json
import subprocess
import sys
from collections.abc import Callable
from pathlib import Path

import pytest

from fitness.contracts import FitnessError, FitnessFunctions
from fitness.features.check.contract import check_fitness_functions, execute_adapter_process


def test_shared_counts_limits_and_source(suite: FitnessFunctions, findings_json: str):
    requests = []

    def execute_adapter(command: list[str], stdin: str | None):
        assert stdin is not None
        requests.append((command, json.loads(stdin)))
        return findings_json

    results = check_fitness_functions(suite, execute_adapter)
    assert [r.status for r in results] == ["FAIL", "PASS", "NOT AUTOMATED"]
    assert [len(r.findings) for r in results] == [1, 1, 0]
    assert results[0].fitness_function.source.endswith("apis.yaml:2")
    assert len(requests) == 1
    assert requests[0][1] == {
        "config": {"preview": True},
        "selections": [
            {"rules": ["API001"], "config": {}},
            {"rules": ["API001"], "config": {}},
        ],
    }
    assert len(suite.warnings) == 1


def test_filter_and_empty_findings(suite: FitnessFunctions):
    def execute_adapter(command: list[str], stdin: str | None):
        assert stdin is not None
        assert len(json.loads(stdin)["selections"]) == 1
        return "[]"

    results = check_fitness_functions(suite, execute_adapter, "migration")
    assert [r.status for r in results] == ["PASS"]


def test_disabled_input(suite: FitnessFunctions):
    suite.tools["example"].send_input = False

    def execute_adapter(command: list[str], stdin: str | None):
        assert stdin is None
        return "[]"

    assert check_fitness_functions(suite, execute_adapter)[0].status == "PASS"


@pytest.mark.parametrize(
    "output",
    [
        "not JSON",
        "{}",
        '[{"tool":"other", "rule_id":"X", "tool_message":"bad"}]',
        '[{"tool":"example", "rule_id":"X"}]',
    ],
)
def test_invalid_tool_output(suite: FitnessFunctions, output: str):
    with pytest.raises(FitnessError, match="tool 'example'"):
        check_fitness_functions(suite, lambda command, stdin: output)


def test_real_subprocess(suite: FitnessFunctions):
    suite.tools["example"].command = [sys.executable, "tests/fixtures/report.py"]
    assert check_fitness_functions(suite, execute_adapter_process)[0].status == "FAIL"


def test_process_failure_is_not_a_violation():
    with pytest.raises(FitnessError, match="exit 7: failure-context"):
        execute_adapter_process(
            [
                sys.executable,
                "-c",
                "import sys; print('failure-context', file=sys.stderr); sys.exit(7)",
            ],
            None,
        )


def test_process_without_input_receives_eof():
    # Give the outer process readable stdin, so inheriting it cannot accidentally pass.
    outer = subprocess.run(
        [
            sys.executable,
            "-c",
            """
import sys
from fitness.features.check.contract import execute_adapter_process
print(execute_adapter_process(
    [sys.executable, '-c', 'import sys; print(repr(sys.stdin.read()))'], None
), end='')
""",
        ],
        input="parent-input-sentinel",
        capture_output=True,
        text=True,
        check=True,
        timeout=5,
    )
    assert outer.stdout == "''\n"


def test_missing_executable(tmp_path: Path):
    with pytest.raises(FitnessError, match="No such file"):
        execute_adapter_process([str(tmp_path / "nonexistent-command")], None)


def test_omitted_rules_count_all_and_warn_on_overlap(
    fitness_functions_from_text: Callable[[str], FitnessFunctions],
):
    suite = fitness_functions_from_text("""
tools:
  example: {command: [example], send_input: true}
functions:
  - {title: All diagnostics, type: test, tool: example}
  - {title: Specific diagnostic, type: test, tool: example, rules: [API001]}
""")

    def execute_adapter(command: list[str], stdin: str | None):
        assert stdin is not None
        assert json.loads(stdin)["selections"][0]["rules"] is None
        return json.dumps(
            [
                {"tool": "example", "rule_id": rule, "tool_message": "Violation"}
                for rule in ["API001", "API002"]
            ]
        )

    assert len(suite.warnings) == 1
    results = check_fitness_functions(suite, execute_adapter)
    assert [[f.rule_id for f in result.findings] for result in results] == [
        ["API001", "API002"],
        ["API001"],
    ]
    assert [result.status for result in results] == ["FAIL", "FAIL"]


@pytest.mark.parametrize(
    ("first", "second", "counts", "warning_count"),
    [
        ("[F]", "[F401]", [0, 1], 0),
        ("[F401]", "[F]", [1, 0], 0),
        ("[E]", "[F401]", [0, 1], 0),
        ("[F, F401]", "[E]", [1, 0], 0),
        ("[F]", "null", [0, 1], 1),
        ("null", "null", [1, 1], 1),
    ],
)
def test_matches_reported_rule_id_exactly(
    fitness_functions_from_text: Callable[[str], FitnessFunctions],
    first: str,
    second: str,
    counts: list[int],
    warning_count: int,
):
    suite = fitness_functions_from_text(f"""
tools:
  example: {{command: [example]}}
functions:
  - {{title: First, type: test, tool: example, rules: {first}}}
  - {{title: Second, type: test, tool: example, rules: {second}}}
""")
    output = '[{"tool":"example", "rule_id":"F401", "tool_message":"Unused import"}]'
    results = check_fitness_functions(suite, lambda command, stdin: output)
    assert [len(result.findings) for result in results] == counts
    assert len(suite.warnings) == warning_count
