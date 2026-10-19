"""Render the shared native controls for standalone Ruff formatting commands."""

from pathlib import Path

import tomli_w
import yaml

if __name__ == "__main__":
    tools = yaml.safe_load(Path("fitness/config.yaml").read_text())["tools"]
    print(tomli_w.dumps(tools["ruff"].get("config", {})), end="")
