"""Validate cross-document references and identify overlapping selections."""

from itertools import combinations

from fitness.contracts import FitnessError, FitnessFunction, Tool


def validate_tool_references(
    tools: dict[str, Tool], fitness_functions: list[FitnessFunction]
) -> None:
    """Reject functions referring to tools absent from the registry.

    Args:
        tools: Registered tools indexed by name.
        fitness_functions: Source-located functions whose references are checked.
    """
    for fitness_function in fitness_functions:
        function = fitness_function.function
        if function.tool and function.tool not in tools:
            raise FitnessError(f"{fitness_function.source}: unknown tool {function.tool!r}")


def find_overlapping_fitness_functions(
    tools: dict[str, Tool], fitness_functions: list[FitnessFunction]
) -> list[str]:
    """Describe function pairs that may count the same adapter findings.

    Args:
        tools: Registered tools indexed by name.
        fitness_functions: Functions whose rule selections are compared.
    """
    warnings = []
    for name in tools:
        automated = [f for f in fitness_functions if f.function.tool == name]
        for left, right in combinations(automated, 2):
            a, b = left.function.rules, right.function.rules
            if a is None or b is None or set(a).intersection(b):
                warnings.append(
                    f"{name}: {left.source} and {right.source} overlap; "
                    "shared findings count toward each function"
                )
    return warnings
