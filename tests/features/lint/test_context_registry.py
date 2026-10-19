from pathlib import Path

import pytest

from fitness.contracts import FitnessError
from fitness.features.lint.contract import lint_fitness_functions


def test_contexts_merge_and_validate_forward_references(tmp_path: Path):
    (tmp_path / "a.yaml").write_text(
        "description: Expectations\nfunctions:\n"
        "  - {title: First, type: architecture, include_in_context: startup}\n"
        "  - {title: Second, type: architecture, include_in_context: [startup, python]}\n"
        "  - {title: Third, type: architecture}\n"
    )
    (tmp_path / "b.yml").write_text("description: Startup\ncontexts: [startup]\n")
    nested = tmp_path / "nested"
    nested.mkdir()
    (nested / "c.yaml").write_text("description: Python\ncontexts: [python]\n")
    loaded = lint_fitness_functions(tmp_path)
    assert loaded.contexts == ["startup", "python"]
    assert [entry.function.include_in_context for entry in loaded.fitness_functions] == [
        ["startup"],
        ["startup", "python"],
        [],
    ]


@pytest.mark.parametrize("across_files", [False, True])
def test_duplicate_context_declarations_fail(tmp_path: Path, across_files: bool):
    (tmp_path / "a.yaml").write_text(
        "description: Registry\ncontexts: "
        + ("[startup]\n" if across_files else "[startup, startup]\n")
    )
    if across_files:
        (tmp_path / "b.yaml").write_text("description: Other\ncontexts: [startup]\n")
    with pytest.raises(FitnessError, match="duplicate context 'startup'"):
        lint_fitness_functions(tmp_path)
