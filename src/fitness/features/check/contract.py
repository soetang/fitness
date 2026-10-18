"""Expose adapter execution and evaluation of fitness-function results."""

from fitness.contracts import Finding, FitnessFunction, FitnessFunctions, Model
from fitness.features.check.adapters import ExecuteAdapter as ExecuteAdapter
from fitness.features.check.adapters import collect_findings
from fitness.features.check.execution import execute_process


def execute_adapter_process(command: list[str], stdin: str | None) -> str:
    """Execute an adapter using the standard process transport.

    Args:
        command: Adapter executable and arguments.
        stdin: Serialized request, or None when no request is sent.

    Returns:
        Captured adapter standard output.
    """
    return execute_process(command, stdin)


class CheckResult(Model):
    """Associate a fitness function with the findings counted against its limit."""

    fitness_function: FitnessFunction
    findings: list[Finding]

    @property
    def status(self) -> str:
        """Return the automation status or the outcome of the violation limit."""
        if not self.fitness_function.function.tool:
            return "NOT AUTOMATED"
        return "PASS" if len(self.findings) <= self.fitness_function.function.limit else "FAIL"


def check_fitness_functions(
    fitness_functions: FitnessFunctions,
    execute_adapter: ExecuteAdapter = execute_adapter_process,
    type_: str | None = None,
) -> list[CheckResult]:
    """Execute each selected tool once and evaluate its functions independently.

    Args:
        fitness_functions: Validated tool registry and source-located functions.
        execute_adapter: Transport accepting command and optional request text.
        type_: Function classification to select, or None to select all types.

    Returns:
        Results in definition order, including manual expectations.

    Raises:
        FitnessError: An adapter fails or returns invalid findings.
    """
    selected = [
        f for f in fitness_functions.fitness_functions if type_ is None or f.function.type == type_
    ]
    findings = collect_findings(fitness_functions.tools, selected, execute_adapter)
    return [
        CheckResult(
            fitness_function=fitness_function,
            findings=[
                f
                for f in findings
                if f.tool == fitness_function.function.tool
                and (
                    fitness_function.function.rules is None
                    or f.rule_id in fitness_function.function.rules
                )
            ],
        )
        for fitness_function in selected
    ]
