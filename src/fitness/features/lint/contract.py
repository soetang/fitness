"""Expose offline validation of fitness definitions."""

from pathlib import Path

from fitness.contracts import FitnessError, FitnessFunctions
from fitness.features.lint.loading import load_fitness_functions
from fitness.features.lint.validation import (
    find_overlapping_fitness_functions,
    validate_tool_references,
)


def lint_fitness_functions(path: Path) -> FitnessFunctions:
    """Load definitions, validate references, and report overlapping selections.

    Args:
        path: YAML file or directory searched recursively for definitions.

    Returns:
        Validated definitions with source locations and overlap warnings.

    Raises:
        FitnessError: Definitions cannot be read or fail validation.
    """
    tools, fitness_functions, contexts = load_fitness_functions(path)
    for entry in fitness_functions:
        for name in entry.function.include_in_context:
            if name not in contexts:
                raise FitnessError(f"{entry.source}: undeclared context {name!r}")
    validate_tool_references(tools, fitness_functions)
    warnings = find_overlapping_fitness_functions(tools, fitness_functions)
    return FitnessFunctions(
        tools=tools, fitness_functions=fitness_functions, contexts=contexts, warnings=warnings
    )
