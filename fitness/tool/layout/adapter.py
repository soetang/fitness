"""Evaluate selected repository layout checks with shared import analysis."""

import json
import re
import sys
import tomllib
from pathlib import Path
from typing import cast

from architecture import (
    contract_findings,
    dependency_findings,
    feature_test_findings,
    file_length_findings,
    token_findings,
)
from imports import scan_imports
from pydantic import BaseModel, ConfigDict, Field, JsonValue


class Settings(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class TokenSettings(Settings):
    budget: int = Field(gt=0)
    encoding: str


class DependencySettings(Settings):
    module_mapping: dict[str, list[str]]


class FileLengthSettings(Settings):
    max_lines: int = Field(gt=0)


class Selection(Settings):
    rules: list[str] | None = None
    config: dict[str, JsonValue] = Field(default_factory=dict)


class Request(Settings):
    config: dict[str, JsonValue] = Field(default_factory=dict, max_length=0)
    selections: list[Selection] = Field(default_factory=list)


def findings(root: Path, request: Request) -> list[dict[str, str]]:
    root = root.resolve()
    results: list[dict[str, str]] = []
    configurations: dict[str, dict[str, JsonValue]] = {}
    for selection in request.selections:
        if selection.rules is None:
            raise ValueError("Layout selections require explicit rule IDs")
        for rule in selection.rules:
            if rule in configurations and configurations[rule] != selection.config:
                raise ValueError(f"Conflicting configuration for {rule}")
            configurations[rule] = selection.config
    setting_types: dict[str, type[Settings]] = {
        "source-test-file-length": FileLengthSettings,
        "feature-test-location": Settings,
        "feature-token-budget": TokenSettings,
        "contract-only-feature-access": Settings,
        "dependency-placement": DependencySettings,
        "adapter-test-location": Settings,
        "adapter-folder": Settings,
        "ruff-config-location": Settings,
        "fitness-owns-ruff-check": Settings,
    }
    validated: dict[str, Settings] = {}
    for rule, config in configurations.items():
        if rule not in setting_types:
            raise ValueError(f"Unsupported layout rule: {rule}")
        validated[rule] = setting_types[rule].model_validate(config)
    imports = (
        scan_imports(
            root,
            source_only=not configurations.keys()
            & {
                "contract-only-feature-access",
                "feature-test-location",
            },
        )
        if configurations.keys()
        & {
            "contract-only-feature-access",
            "dependency-placement",
            "feature-test-location",
        }
        else {}
    )
    for rule, config in validated.items():
        if rule == "source-test-file-length":
            file_settings = cast(FileLengthSettings, config)
            results.extend(file_length_findings(root, file_settings.max_lines))
        elif rule == "feature-test-location":
            results.extend(feature_test_findings(root, imports))
        elif rule == "feature-token-budget":
            settings = cast(TokenSettings, config)
            results.extend(token_findings(root, settings.budget, settings.encoding))
        elif rule == "contract-only-feature-access":
            results.extend(contract_findings(root, imports))
        elif rule == "dependency-placement":
            settings = cast(DependencySettings, config)
            project_path = root / "pyproject.toml"
            project = tomllib.loads(project_path.read_text()) if project_path.exists() else {}
            metadata = project.get("project", {})
            dependencies = list(metadata.get("dependencies", []))
            for group in metadata.get("optional-dependencies", {}).values():
                dependencies.extend(group)
            results.extend(
                dependency_findings(
                    root,
                    imports,
                    dependencies,
                    settings.module_mapping,
                    project.get("build-system", {}).get("requires", []),
                )
            )
        elif rule == "adapter-test-location":
            results.extend(adapter_test_findings(root))
        elif rule == "adapter-folder":
            results.extend(adapter_folder_findings(root))
        elif rule == "ruff-config-location":
            results.extend(ruff_config_findings(root))
        elif rule == "fitness-owns-ruff-check":
            results.extend(ruff_check_findings(root))
    return results


def adapter_test_findings(root: Path) -> list[dict[str, str]]:
    misplaced = list((root / "tests").rglob("test_*adapter*.py"))
    misplaced.extend(
        path
        for path in (root / "fitness" / "tool").rglob("test_*.py")
        if not (path.parent / "adapter.py").is_file()
    )
    return [
        {
            "tool": "layout",
            "rule_id": "adapter-test-location",
            "tool_message": "Adapter tests belong in fitness/tool/<name>/ beside adapter.py.",
            "filename": str(path.relative_to(root)),
        }
        for path in sorted(misplaced)
        if path.is_file()
    ]


def adapter_folder_findings(root: Path) -> list[dict[str, str]]:
    return [
        {
            "tool": "layout",
            "rule_id": "adapter-folder",
            "tool_message": "Use fitness/tool/<name>/adapter.py with colocated test_*.py files.",
            "filename": str(path.relative_to(root)),
        }
        for path in sorted((root / "fitness" / "tool").rglob("*.py"))
        if (path.name == "adapter.py" or path.name.endswith("_adapter.py"))
        and not path.name.startswith("test_")
        and (
            path.name != "adapter.py"
            or path.parent.parent != root / "fitness" / "tool"
            or not any(path.parent.glob("test_*.py"))
        )
    ]


def ruff_config_findings(root: Path) -> list[dict[str, str]]:
    results = []
    project = root / "pyproject.toml"
    if project.is_file() and "ruff" in tomllib.loads(project.read_text()).get("tool", {}):
        results.append(
            {
                "tool": "layout",
                "rule_id": "ruff-config-location",
                "tool_message": (
                    "Move Ruff configuration into fitness/tool.yaml or fitness/functions/."
                ),
                "filename": "pyproject.toml",
            }
        )
    return results


def ruff_check_findings(root: Path) -> list[dict[str, str]]:
    results = []
    justfile = root / "justfile"
    if justfile.is_file():
        results.extend(
            {
                "tool": "layout",
                "rule_id": "fitness-owns-ruff-check",
                "tool_message": f"Line {number}: run Ruff lint checks through Fitness.",
                "filename": "justfile",
            }
            for number, line in enumerate(justfile.read_text().splitlines(), start=1)
            if line[:1].isspace()
            and not line.lstrip().startswith("#")
            and re.search(r"\bruff\s+check\b", line)
        )
    return results


if __name__ == "__main__":
    root = Path(sys.argv[1]) if len(sys.argv) > 1 else Path.cwd()
    request = Request.model_validate_json(sys.stdin.read() or "{}")
    print(json.dumps(findings(root, request)))
