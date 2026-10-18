"""Define options shared by fitness CLI commands."""

from pathlib import Path
from typing import Annotated

import typer

Rules = Annotated[Path, typer.Option("--rules", help="YAML file or directory of definitions.")]
