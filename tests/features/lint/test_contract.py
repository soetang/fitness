from collections.abc import Callable
from pathlib import Path

import pytest

from fitness.contracts import FitnessError
from fitness.features.lint.contract import lint_fitness_functions


@pytest.mark.parametrize(
    ("function", "diagnostic"),
    [
        ("{title: Test, type: custom, typo: true}", "extra_forbidden"),
        ("{title: Test, type: custom, limit: -1}", "greater_than_equal"),
        ("{title: Test, type: custom, limit: true}", "int_type"),
        ("{title: Test, type: custom, tool: missing, rules: [X]}", "unknown tool 'missing'"),
        ("{title: Test, type: custom, rules: [X]}", "rules and config require a tool"),
        ("{title: Test, type: custom, tool: example, rules: []}", "too_short"),
        ("{title: Test, title: Duplicate, type: custom}", "duplicate YAML key"),
        ("{title: Test, type: custom, tool: example, rules: [X, X]}", "duplicate rule IDs"),
    ],
)
def test_invalid_fitness_functions(
    write_definitions: Callable[[str], Path], function: str, diagnostic: str
):
    document = "tools: {example: {command: [example]}}\nfunctions: [" + function + "]"
    with pytest.raises(FitnessError, match=diagnostic):
        lint_fitness_functions(write_definitions(document))


@pytest.mark.parametrize(
    ("document", "diagnostic"),
    [
        ("? [invalid, key]\n: value", "YAML mapping keys must be scalar"),
        (
            "tools: {example: {command: [example], config: {date: 2026-10-18}}}",
            "invalid-json-value",
        ),
        ("functions: [", "expected the node content"),
        ("", "model_type"),
    ],
)
def test_invalid_documents(
    write_definitions: Callable[[str], Path], document: str, diagnostic: str
):
    with pytest.raises(FitnessError, match=diagnostic):
        lint_fitness_functions(write_definitions(document))


def test_omitted_rules_are_valid(write_definitions: Callable[[str], Path]):
    fitness_functions = lint_fitness_functions(
        write_definitions(
            "tools: {example: {command: [example]}}\n"
            "functions: [{title: Test, type: custom, tool: example}]"
        )
    )
    assert fitness_functions.fitness_functions[0].function.rules is None


def test_duplicate_tools(tmp_path: Path):
    for name in ["a.yaml", "b.yaml"]:
        (tmp_path / name).write_text("tools: {example: {command: [example]}}")
    with pytest.raises(FitnessError, match="duplicate tool"):
        lint_fitness_functions(tmp_path)


def test_empty_directory(tmp_path: Path):
    with pytest.raises(FitnessError, match="no YAML definitions found"):
        lint_fitness_functions(tmp_path)
