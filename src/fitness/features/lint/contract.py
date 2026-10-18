from pathlib import Path

from fitness.contracts import FitnessFunctions
from fitness.features.lint.loading import load_fitness_functions
from fitness.features.lint.validation import (
    find_overlapping_fitness_functions,
    validate_tool_references,
)


def lint_fitness_functions(path: Path) -> FitnessFunctions:
    tools, fitness_functions = load_fitness_functions(path)
    validate_tool_references(tools, fitness_functions)
    warnings = find_overlapping_fitness_functions(tools, fitness_functions)
    return FitnessFunctions(tools=tools, fitness_functions=fitness_functions, warnings=warnings)
