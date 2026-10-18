"""Run fitness checks and present failures through the check command."""

from pathlib import Path
from typing import Annotated

import typer

from fitness.cli.options import Rules
from fitness.contracts import Finding, FitnessError
from fitness.features.check.contract import CheckResult, ExecuteAdapter, check_fitness_functions
from fitness.features.lint.contract import lint_fitness_functions


def register(app: typer.Typer, execute_adapter: ExecuteAdapter) -> None:
    """Bind the check command to this application's adapter transport.

    Args:
        app: Command-line application receiving the check command.
        execute_adapter: Transport captured by the command callback.
    """

    @app.command()
    def check(
        rules: Rules = Path("fitness"),
        type_: Annotated[str | None, typer.Option("--type")] = None,
    ):
        """Run configured tools and compare findings with violation limits."""
        try:
            results = check_fitness_functions(lint_fitness_functions(rules), execute_adapter, type_)
        except FitnessError as error:
            typer.echo(f"ERROR  {error}", err=True)
            raise typer.Exit(2) from error
        raise typer.Exit(_present_fitness_check_results(results))


def _format_finding(finding: Finding) -> str:
    """Format an adapter diagnostic with its optional source location.

    Args:
        finding: Diagnostic to display.
    """
    place = finding.filename or ""
    if finding.location:
        place += f":{finding.location.row}:{finding.location.column}"
    prefix = f"{place} · " if place else ""
    return f"\n{prefix}{finding.tool} / {finding.rule_id}\n{finding.tool_message}"


def _present_failed_fitness_function(result: CheckResult) -> None:
    """Print a failed function's limit, guidance, and individual findings.

    Args:
        result: Failed evaluation to display.
    """
    function = result.fitness_function.function
    typer.echo(f"{result.status}  {function.title}\n{result.fitness_function.source}")
    typer.echo(f"{len(result.findings)} violations · limit: {function.limit}")
    if function.guidance:
        typer.echo(f"\nGuidance:\n{function.guidance}")
    for finding in result.findings:
        typer.echo(_format_finding(finding))
    typer.echo()


def _present_fitness_check_results(results: list[CheckResult]) -> int:
    """Print failures or a success summary and return the corresponding exit code.

    Args:
        results: Evaluations whose failed entries should be displayed.
    """
    failures = [result for result in results if result.status == "FAIL"]
    if not failures:
        typer.echo("success")
        return 0
    for result in failures:
        _present_failed_fitness_function(result)
    return 1
