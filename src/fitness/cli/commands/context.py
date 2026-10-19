"""Render selected fitness functions as agent context."""

from pathlib import Path
from typing import Annotated

import typer

from fitness.cli.options import Rules
from fitness.contracts import FitnessError
from fitness.features.context.contract import ContextResult, select_context
from fitness.features.lint.contract import lint_fitness_functions


def present_context(result: ContextResult, json_: bool) -> None:
    """Write selected context without emitting a blank line for empty Markdown.

    Args:
        result: Selected source-located functions.
        json_: Whether to emit the complete structured result.
    """
    output = result.model_dump_json(indent=2) if json_ else result.markdown()
    if output:
        typer.echo(output)


def register(app: typer.Typer) -> None:
    """Bind context selection to the application.

    Args:
        app: Command-line application receiving the context command.
    """

    @app.command()
    def context(
        name: str,
        rules: Rules = Path("fitness"),
        json_: Annotated[bool, typer.Option("--json", help="Emit full structured JSON.")] = False,
    ):
        """Print expectations explicitly included in a registered context."""
        try:
            result = select_context(lint_fitness_functions(rules), name)
        except FitnessError as error:
            typer.echo(f"ERROR  {error}", err=True)
            raise typer.Exit(2) from error
        present_context(result, json_)
