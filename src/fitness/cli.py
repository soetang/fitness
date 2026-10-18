"""Present fitness validation and check results through the command line."""

from pathlib import Path
from typing import Annotated

import typer

from fitness.contracts import Finding, FitnessError
from fitness.features.check.contract import (
    CheckResult,
    ExecuteAdapter,
    check_fitness_functions,
    execute_adapter_process,
)
from fitness.features.lint.contract import lint_fitness_functions

Rules = Annotated[Path, typer.Option("--rules", help="YAML file or directory of definitions.")]


def format_finding(finding: Finding) -> str:
    """Format an adapter diagnostic with its optional source location.

    Args:
        finding: Diagnostic to display.
    """
    place = finding.filename or ""
    if finding.location:
        place += f":{finding.location.row}:{finding.location.column}"
    prefix = f"{place} · " if place else ""
    return f"\n{prefix}{finding.tool} / {finding.rule_id}\n{finding.tool_message}"


def present_failed_fitness_function(result: CheckResult) -> None:
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
        typer.echo(format_finding(finding))
    typer.echo()


def present_fitness_check_results(results: list[CheckResult]) -> int:
    """Print failures or a success summary and return the corresponding exit code.

    Args:
        results: Evaluations whose failed entries should be displayed.
    """
    failures = [result for result in results if result.status == "FAIL"]
    if not failures:
        typer.echo("success")
        return 0
    for result in failures:
        present_failed_fitness_function(result)
    return 1


def create_app(execute_adapter: ExecuteAdapter = execute_adapter_process) -> typer.Typer:
    """Build the CLI with an injectable adapter transport.

    Args:
        execute_adapter: Transport used by the check command to invoke adapters.
    """
    app = typer.Typer(no_args_is_help=True, pretty_exceptions_enable=False)

    @app.command()
    def lint(rules: Rules = Path("fitness"), verbose: bool = False):
        """Validate definitions and references offline."""
        try:
            suite = lint_fitness_functions(rules)
        except FitnessError as error:
            typer.echo(f"ERROR  {error}", err=True)
            raise typer.Exit(2) from error
        for warning in suite.warnings:
            typer.echo(f"WARNING  {warning}")
        typer.echo("Valid fitness definitions")
        if verbose:
            typer.echo(f"{len(suite.fitness_functions)} functions · {len(suite.tools)} tools")

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
        raise typer.Exit(present_fitness_check_results(results))

    return app


app = create_app()
