"""Check the prospective commit, rather than unstaged working-tree changes."""

import json
import subprocess
import sys
from pathlib import Path


def findings(root: Path) -> list[dict[str, str]]:
    result = subprocess.run(
        ["git", "diff", "--cached", "--name-only", "--no-renames", "-z"],
        cwd=root,
        capture_output=True,
        text=True,
        check=True,
    )
    paths = result.stdout.split("\0")
    return [*_definition_implementation_findings(paths), *_feature_boundary_findings(paths)]


def _definition_implementation_findings(paths: list[str]) -> list[dict[str, str]]:
    """Keep fitness definitions and source/test changes in separate commits."""
    definitions = [path for path in paths if path.startswith("fitness/")]
    implementation = [path for path in paths if path.startswith(("src/", "tests/"))]
    if not definitions or not implementation:
        return []
    return [
        _commit_finding(
            "separate-definition-and-implementation-changes",
            "Split the staged changes into separate commits. "
            f"Fitness functions/tools: {', '.join(definitions)}. "
            f"Source/tests: {', '.join(implementation)}.",
        )
    ]


def _feature_boundary_findings(paths: list[str]) -> list[dict[str, str]]:
    """Keep each commit's feature changes within one feature boundary."""
    features = set()
    for path in paths:
        parts = Path(path).parts
        for prefix in (("src", "fitness", "features"), ("tests", "features"), ("docs", "features")):
            if parts[: len(prefix)] == prefix and len(parts) > len(prefix) + 1:
                features.add(parts[len(prefix)])
    if len(features) <= 1:
        return []
    return [
        _commit_finding(
            "one-feature-per-commit",
            "Split staged edits across features: " + ", ".join(sorted(features)),
        )
    ]


def _commit_finding(rule: str, message: str) -> dict[str, str]:
    """Build the common diagnostic envelope for a commit policy."""
    return {"tool": "commits", "rule_id": rule, "tool_message": message}


if __name__ == "__main__":
    print(json.dumps(findings(Path(sys.argv[1]) if len(sys.argv) > 1 else Path.cwd())))
