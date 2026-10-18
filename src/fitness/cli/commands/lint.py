"""Validate definitions offline through the lint command."""

from pathlib import Path

import typer

from fitness.cli.options import Rules
from fitness.contracts import FitnessError
from fitness.features.lint.contract import lint_fitness_functions


def register(app: typer.Typer) -> None:
    """Register the offline validation command.

    Args:
        app: Command-line application receiving the lint command.
    """
    app.command(help="Validate definitions and references offline.")(lint)


def lint(rules: Rules = Path("fitness"), verbose: bool = False):
    """Validate definitions and references offline.

    Args:
        rules: YAML file or directory containing fitness definitions.
        verbose: Whether to display validated function and tool counts.
    """
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
