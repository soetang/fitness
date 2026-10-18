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
        own_feature, shared = _feature_access_context(relative)
        offenders = {
            (module, row)
            for module, row in references
            if _violates_feature_boundary(module, own_feature, shared)
        }
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


def _feature_access_context(relative: Path) -> tuple[str | None, bool]:
    """Identify the caller's own feature and whether it defines shared contracts."""
    parts = list(relative.with_suffix("").parts)
    if parts[0] == "src":
        parts.pop(0)
    own_feature = parts[2] if parts[:2] == ["fitness", "features"] and len(parts) > 3 else None
    return own_feature, parts[:2] == ["fitness", "contracts"]


def _violates_feature_boundary(module: str, own_feature: str | None, shared: bool) -> bool:
    """Allow local implementation access and external access through contracts."""
    parts = module.split(".")
    if parts[:2] != ["fitness", "features"]:
        return False
    if len(parts) > 2 and parts[2] == own_feature:
        return False
    return shared or len(parts) <= 3 or parts[3] != "contract"


def token_findings(root: Path, budget: int, encoding_name: str) -> list[dict[str, str]]:
    if encoding_name not in tiktoken.list_encoding_names():
        tiktoken.get_encoding(encoding_name)
    features_root = root / "src/fitness/features"
    features = (
        sorted(
            path
            for path in features_root.iterdir()
            if path.is_dir() and not path.name.startswith(("_", ".")) and not path.is_symlink()
        )
        if (features_root.is_dir())
        else []
    )
    results = []
    for feature in features:
        paths = _feature_content_paths(root, feature)
        count = _token_count_when_over_budget(paths, budget, encoding_name)
        if count > budget:
            results.append(
                report(
                    "feature-token-budget",
                    f"{feature.name}: {count} tokens exceeds {budget}.",
                    feature.relative_to(root).as_posix(),
                )
            )
    return results


def _feature_content_paths(root: Path, feature: Path) -> list[Path]:
    """Select feature content without following symlinks or generated directories."""
    return [
        path
        for path in feature.rglob("*")
        if path.is_file()
        and not any(parent.is_symlink() for parent in (path, *path.parents) if parent != root)
        and not any(
            part.startswith(".") or part == "__pycache__" for part in path.relative_to(root).parts
        )
        and path.suffix in {".py", ".md", ".yaml", ".yml", ".json", ".toml", ".txt"}
    ]


def _token_count_when_over_budget(paths: list[Path], budget: int, encoding_name: str) -> int:
    """Avoid tokenizer initialization when UTF-8 bytes already prove the budget fits."""
    contents = [path.read_bytes().decode("utf-8") for path in sorted(paths)]
    # Each ordinary-text token consumes at least one UTF-8 byte. Decode first so
    # the shortcut cannot hide invalid UTF-8, and retain per-file tokenization.
    if sum(len(text.encode("utf-8")) for text in contents) <= budget:
        return 0
    encoding = tiktoken.get_encoding(encoding_name)
    return sum(len(encoding.encode(text, disallowed_special=())) for text in contents)


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
