"""Assemble the fitness command-line application."""

import typer

from fitness.cli.commands import check, context, lint
from fitness.features.check.contract import ExecuteAdapter, execute_adapter_process


def create_app(execute_adapter: ExecuteAdapter = execute_adapter_process) -> typer.Typer:
    """Build the CLI with an injectable adapter transport.

    Args:
        execute_adapter: Transport used by the check command to invoke adapters.
    """
    app = typer.Typer(no_args_is_help=True, pretty_exceptions_enable=False)
    lint.register(app)
    context.register(app)
    check.register(app, execute_adapter)
    return app


app = create_app()
