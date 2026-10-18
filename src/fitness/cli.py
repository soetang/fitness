from pathlib import Path
from typing import Annotated

import typer

from fitness.contracts import FitnessError
from fitness.features.check.contract import (
    ExecuteAdapter,
    check_fitness_functions,
    execute_adapter_process,
)
from fitness.features.lint.contract import lint_fitness_functions

Rules = Annotated[Path, typer.Option("--rules", help="YAML file or directory of definitions.")]


def create_app(execute_adapter: ExecuteAdapter = execute_adapter_process) -> typer.Typer:
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
        failures = [result for result in results if result.status == "FAIL"]
        if not failures:
            typer.echo("success")
            raise typer.Exit(0)
        for result in failures:
            function = result.fitness_function.function
            typer.echo(f"{result.status}  {function.title}\n{result.fitness_function.source}")
            typer.echo(f"{len(result.findings)} violations · limit: {function.limit}")
            if function.guidance:
                typer.echo(f"\nGuidance:\n{function.guidance}")
            for finding in result.findings:
                place = finding.filename or ""
                if finding.location:
                    place += f":{finding.location.row}:{finding.location.column}"
                prefix = f"{place} · " if place else ""
                typer.echo(f"\n{prefix}{finding.tool} / {finding.rule_id}\n{finding.tool_message}")
            typer.echo()
        raise typer.Exit(1)

    return app


app = create_app()
