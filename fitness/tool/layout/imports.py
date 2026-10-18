"""Collect one reusable import inventory with one Semgrep invocation."""

import importlib.util
import json
import os
import subprocess
from importlib.metadata import distribution
from pathlib import Path
from tempfile import NamedTemporaryFile

from pydantic import BaseModel, JsonValue


class Position(BaseModel):
    line: int
    offset: int


class MatchDetails(BaseModel):
    message: str


class Match(BaseModel):
    check_id: str
    path: str
    start: Position
    end: Position
    extra: MatchDetails


class ScanPaths(BaseModel):
    scanned: list[str]


class ScanResult(BaseModel):
    results: list[Match]
    errors: list[JsonValue]
    paths: ScanPaths


def python_files(root: Path) -> list[Path]:
    paths = []
    for directory, folders, files in os.walk(root, followlinks=False):
        folders[:] = sorted(
            name
            for name in folders
            if not name.startswith(".")
            and name not in {"__pycache__", "dist", "build"}
            and not (Path(directory) / name).is_symlink()
        )
        paths.extend(
            Path(directory) / name
            for name in sorted(files)
            if name.endswith(".py") and not (Path(directory) / name).is_symlink()
        )
    return paths


def scan_imports(root: Path, source_only: bool = False) -> dict[Path, list[tuple[str, int]]]:
    root = root.resolve()
    paths = python_files(root / "src" if source_only else root)
    if not paths:
        return {}
    binary = distribution("semgrep").locate_file("semgrep/bin/semgrep-core")
    targets = [
        "Targets",
        [
            [
                "CodeTarget",
                {
                    "path": {"fpath": str(path), "ppath": "/" + path.relative_to(root).as_posix()},
                    "analyzer": "python",
                    "products": ["sast"],
                },
            ]
            for path in paths
        ],
    ]
    with NamedTemporaryFile(mode="w", encoding="utf-8") as target_file:
        json.dump(targets, target_file)
        target_file.flush()
        process = subprocess.run(
            [
                str(binary),
                "-rules",
                str(Path(__file__).with_name("imports.semgrep")),
                "-targets",
                target_file.name,
                "-json_nodots",
                "-j",
                "1",
            ],
            cwd=root,
            capture_output=True,
            text=True,
            check=False,
            timeout=45,
        )
    if process.returncode:
        raise ValueError(f"Semgrep exited {process.returncode}: {process.stderr or process.stdout}")
    scan = ScanResult.model_validate_json(process.stdout)
    if scan.errors:
        raise ValueError(f"Semgrep analysis errors: {scan.errors}")
    if set(map(Path, scan.paths.scanned)) != set(paths):
        raise ValueError("Semgrep did not completely analyze the requested Python files")
    references: dict[Path, list[tuple[str, int]]] = {path: [] for path in paths}
    source_bytes: dict[str, bytes] = {}
    accesses = {
        (match.path, match.start.offset)
        for match in scan.results
        if match.check_id == "feature-access"
    }
    for match in scan.results:
        if match.check_id in {"feature-access", "feature-package-access"}:
            if match.path not in source_bytes:
                source_bytes[match.path] = Path(match.path).read_bytes()
            expression = source_bytes[match.path][match.start.offset : match.end.offset]
            # Alias-only expressions are already covered by their import facts.
            # Semgrep's substituted metavariables can retain the local alias text.
            if expression.count(b".") < (3 if match.check_id == "feature-access" else 2):
                continue
        if (
            match.check_id == "feature-package-access"
            and (match.path, match.start.offset) in accesses
        ):
            continue
        path = Path(match.path)
        parts = list(path.relative_to(root).with_suffix("").parts)
        if parts[0] == "src":
            parts.pop(0)
        package = ".".join(parts[:-1])
        module = match.extra.message
        if match.check_id == "from-import":
            module, symbol = module.split("|", 1)
            module = importlib.util.resolve_name(module, package) + "." + symbol
        elif match.check_id == "relative-dynamic-import":
            package, module = module.split("|", 1)
        module = importlib.util.resolve_name(module, package)
        references[path].append((module, match.start.line))
    return references
