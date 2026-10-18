"""Evaluate selected repository layout checks with shared import analysis."""

import json
import re
import sys
import tomllib
from collections.abc import Callable
from pathlib import Path

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
    configurations = validate_layout_selections(request)
    imports = analyze_selected_imports(root, set(configurations))
    results: list[dict[str, str]] = []
    for rule, settings in configurations.items():
        results.extend(evaluate_layout_selection(root, rule, settings, imports))
    return results


def collect_layout_selections(request: Request) -> dict[str, dict[str, JsonValue]]:
    configurations: dict[str, dict[str, JsonValue]] = {}
    for selection in request.selections:
        if selection.rules is None:
            raise ValueError("Layout selections require explicit rule IDs")
        for rule in selection.rules:
            if rule in configurations and configurations[rule] != selection.config:
                raise ValueError(f"Conflicting configuration for {rule}")
            configurations[rule] = selection.config
    return configurations


def validate_layout_selections(request: Request) -> dict[str, Settings]:
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
    for rule, config in collect_layout_selections(request).items():
        if rule not in setting_types:
            raise ValueError(f"Unsupported layout rule: {rule}")
        validated[rule] = setting_types[rule].model_validate(config)
    return validated


def analyze_selected_imports(
    root: Path, selected_rules: set[str]
) -> dict[Path, list[tuple[str, int]]]:
    return (
        scan_imports(
            root,
            source_only=not selected_rules
            & {
                "contract-only-feature-access",
                "feature-test-location",
            },
        )
        if selected_rules
        & {
            "contract-only-feature-access",
            "dependency-placement",
            "feature-test-location",
        }
        else {}
    )


def check_runtime_dependency_usage(
    root: Path, settings: DependencySettings, imports: dict[Path, list[tuple[str, int]]]
) -> list[dict[str, str]]:
    project_path = root / "pyproject.toml"
    project = tomllib.loads(project_path.read_text()) if project_path.exists() else {}
    metadata = project.get("project", {})
    dependencies = list(metadata.get("dependencies", []))
    for group in metadata.get("optional-dependencies", {}).values():
        dependencies.extend(group)
    return dependency_findings(
        root,
        imports,
        dependencies,
        settings.module_mapping,
        project.get("build-system", {}).get("requires", []),
    )


def evaluate_layout_selection(
    root: Path, rule: str, settings: Settings, imports: dict[Path, list[tuple[str, int]]]
) -> list[dict[str, str]]:
    if isinstance(settings, FileLengthSettings):
        return file_length_findings(root, settings.max_lines)
    if isinstance(settings, TokenSettings):
        return token_findings(root, settings.budget, settings.encoding)
    if isinstance(settings, DependencySettings):
        return check_runtime_dependency_usage(root, settings, imports)
    import_checks = {
        "feature-test-location": feature_test_findings,
        "contract-only-feature-access": contract_findings,
    }
    if rule in import_checks:
        return import_checks[rule](root, imports)
    repository_checks: dict[str, Callable[[Path], list[dict[str, str]]]] = {
        "adapter-test-location": adapter_test_findings,
        "adapter-folder": adapter_folder_findings,
        "ruff-config-location": ruff_config_findings,
        "fitness-owns-ruff-check": ruff_check_findings,
    }
    return repository_checks[rule](root)


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
