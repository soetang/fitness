from pathlib import Path
from typing import Annotated

import typer

from fitness.core import FitnessError, Runner, evaluate, load, run_command

Rules = Annotated[Path, typer.Option("--rules", help="YAML file or directory of definitions.")]


def create_app(runner: Runner = run_command) -> typer.Typer:
    app = typer.Typer(no_args_is_help=True, pretty_exceptions_enable=False)

    @app.command()
    def lint(rules: Rules = Path("fitness"), verbose: bool = False):
        """Validate definitions and references offline."""
        try:
            suite = load(rules)
        except FitnessError as error:
            typer.echo(f"ERROR  {error}", err=True)
            raise typer.Exit(2) from error
        for warning in suite.warnings:
            typer.echo(f"WARNING  {warning}")
        typer.echo("Valid fitness definitions")
        if verbose:
            typer.echo(f"{len(suite.definitions)} functions · {len(suite.tools)} tools")

    @app.command()
    def check(
        rules: Rules = Path("fitness"),
        type_: Annotated[str | None, typer.Option("--type")] = None,
    ):
        """Run configured tools and compare findings with violation limits."""
        try:
            results = evaluate(load(rules), runner, type_)
        except FitnessError as error:
            typer.echo(f"ERROR  {error}", err=True)
            raise typer.Exit(2) from error
        if not results:
            typer.echo("No matching fitness functions")
        for result in results:
            function = result.definition.function
            typer.echo(f"{result.status}  {function.title}\n{result.definition.source}")
            if function.tool:
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
        raise typer.Exit(1 if any(r.status == "FAIL" for r in results) else 0)

    return app


app = create_app()
