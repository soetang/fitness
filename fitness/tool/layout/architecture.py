"""Repository architecture analysis used by the layout adapter."""

from pathlib import Path

import tiktoken
from imports import python_files
from packaging.requirements import Requirement
from packaging.utils import canonicalize_name


def report(rule: str, message: str, filename: str) -> dict[str, str]:
    return {"tool": "layout", "rule_id": rule, "tool_message": message, "filename": filename}


def file_length_findings(root: Path, max_lines: int) -> list[dict[str, str]]:
    results = []
    for directory in (root / "src", root / "tests"):
        for path in python_files(directory):
            count = len(path.read_text(encoding="utf-8").splitlines())
            if count > max_lines:
                results.append(
                    report(
                        "source-test-file-length",
                        f"{count} lines exceeds {max_lines}.",
                        path.relative_to(root).as_posix(),
                    )
                )
    return results


def feature_test_findings(
    root: Path,
    imports: dict[Path, list[tuple[str, int]]],
) -> list[dict[str, str]]:
    results = []
    for path, references in imports.items():
        if not path.is_relative_to(root / "tests") or not (
            path.name.startswith("test_") or path.name.endswith("_test.py")
        ):
            continue
        features = {
            name.split(".")[2]
            for name, _ in references
            if name.startswith("fitness.features.") and len(name.split(".")) > 2
        }
        for feature in sorted(features):
            expected = root / "tests/features" / feature
            if not path.is_relative_to(expected):
                results.append(
                    report(
                        "feature-test-location",
                        f"Tests of {feature} belong in tests/features/{feature}/.",
                        path.relative_to(root).as_posix(),
                    )
                )
    return results


def contract_findings(
    root: Path, imports: dict[Path, list[tuple[str, int]]]
) -> list[dict[str, str]]:
    results = []
    for path, references in imports.items():
        relative = path.relative_to(root)
        module_parts = list(relative.with_suffix("").parts)
        if module_parts[0] == "src":
            module_parts.pop(0)
        own_feature = (
            module_parts[2]
            if module_parts[:2] == ["fitness", "features"] and len(module_parts) > 3
            else None
        )
        shared = module_parts[:2] == ["fitness", "contracts"]
        offenders = set()
        for module, row in references:
            parts = module.split(".")
            if parts[:2] != ["fitness", "features"]:
                continue
            if len(parts) > 2 and parts[2] == own_feature:
                continue
            if not shared and len(parts) > 3 and parts[3] == "contract":
                continue
            offenders.add((module, row))
        for module, row in sorted(offenders):
            results.append(
                report(
                    "contract-only-feature-access",
                    f"Line {row}: {module}: "
                    + (
                        "shared contracts cannot depend on features."
                        if shared
                        else "enter another feature through its contract."
                    ),
                    relative.as_posix(),
                )
            )
    return results


def token_findings(
    root: Path, budget: int, encoding_name: str, associated_files: dict[str, list[str]]
) -> list[dict[str, str]]:
    encoding = tiktoken.get_encoding(encoding_name)
    features_root = root / "src/fitness/features"
    features = (
        sorted(path for path in features_root.iterdir() if path.is_dir())
        if (features_root.is_dir())
        else []
    )
    feature_names = {path.name for path in features if not path.name.startswith("_")}
    if set(associated_files) - feature_names:
        raise ValueError("Associated files reference an unknown feature")
    results = []
    for feature in features:
        if feature.name not in feature_names:
            continue
        paths: set[Path] = set()
        patterns = [
            f"src/fitness/features/{feature.name}/**/*",
            f"tests/features/{feature.name}/**/*",
            f"docs/features/{feature.name}/**/*",
            *associated_files.get(feature.name, []),
        ]
        for pattern in patterns:
            if Path(pattern).is_absolute() or ".." in Path(pattern).parts:
                raise ValueError("Feature file patterns must stay within the repository")
            paths.update(
                path
                for path in root.glob(pattern)
                if path.is_file()
                and not any(
                    parent.is_symlink() for parent in (path, *path.parents) if parent != root
                )
                and not any(
                    part.startswith(".") or part == "__pycache__"
                    for part in path.relative_to(root).parts
                )
                and path.suffix in {".py", ".md", ".yaml", ".yml", ".json", ".toml", ".txt"}
            )
        count = sum(
            len(encoding.encode(path.read_bytes().decode("utf-8"), disallowed_special=()))
            for path in sorted(paths)
        )
        if count > budget:
            results.append(
                report(
                    "feature-token-budget",
                    f"{feature.name}: {count} tokens exceeds {budget}.",
                    feature.relative_to(root).as_posix(),
                )
            )
    return results


def dependency_findings(
    root: Path,
    imports: dict[Path, list[tuple[str, int]]],
    dependencies: list[str],
    module_mapping: dict[str, list[str]],
    build_requirements: list[str],
) -> list[dict[str, str]]:
    used = {
        name.split(".")[0]
        for path, references in imports.items()
        if path.is_relative_to(root / "src")
        for name, _ in references
    }
    mapping = {canonicalize_name(name): modules for name, modules in module_mapping.items()}
    build_names = {canonicalize_name(Requirement(value).name) for value in build_requirements}
    results = []
    for dependency in sorted(set(dependencies)):
        name = canonicalize_name(Requirement(dependency).name)
        if name not in mapping:
            raise ValueError(f"No explicit distribution/import mapping for {name}")
        if not set(mapping[name]).intersection(used):
            destination = "build-system.requires" if name in build_names else "the dev group"
            results.append(
                report(
                    "dependency-placement",
                    f"{name} is not imported in src/; keep it in {destination}.",
                    "pyproject.toml",
                )
            )
    return results
