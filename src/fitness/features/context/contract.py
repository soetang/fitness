"""Expose named context selection independently of delivery and adapter execution."""

from fitness.contracts import FitnessError, FitnessFunction, FitnessFunctions, Model


class ContextResult(Model):
    """Contain a named context and its complete source-located expectations."""

    context: str
    fitness_functions: list[FitnessFunction]

    def markdown(self) -> str:
        """Render titles and optional guidance, with no output for empty contexts."""
        return "\n\n".join(
            f"## {entry.function.title}"
            + (f"\n\n{entry.function.guidance}" if entry.function.guidance else "")
            for entry in self.fitness_functions
        )


def select_context(fitness_functions: FitnessFunctions, name: str) -> ContextResult:
    """Select a registered context in definition order without running adapters.

    Args:
        fitness_functions: Loaded and validated definitions.
        name: Exact user-defined context name to select.

    Raises:
        FitnessError: The requested context is not registered.
    """
    if name not in fitness_functions.contexts:
        raise FitnessError(f"undeclared context {name!r}")
    return ContextResult(
        context=name,
        fitness_functions=[
            entry
            for entry in fitness_functions.fitness_functions
            if name in entry.function.include_in_context
        ],
    )
