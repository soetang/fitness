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
    definitions = [path for path in paths if path.startswith("fitness/")]
    implementation = [path for path in paths if path.startswith(("src/", "tests/"))]
    results = []
    if definitions and implementation:
        results.extend(
            [
                {
                    "tool": "commits",
                    "rule_id": "separate-definition-and-implementation-changes",
                    "tool_message": (
                        "Split the staged changes into separate commits. "
                        f"Fitness functions/tools: {', '.join(definitions)}. "
                        f"Source/tests: {', '.join(implementation)}."
                    ),
                }
            ]
        )
    features = set()
    for path in paths:
        parts = Path(path).parts
        for prefix in (("src", "fitness", "features"), ("tests", "features"), ("docs", "features")):
            if parts[: len(prefix)] == prefix and len(parts) > len(prefix) + 1:
                features.add(parts[len(prefix)])
    if len(features) > 1:
        results.append(
            {
                "tool": "commits",
                "rule_id": "one-feature-per-commit",
                "tool_message": "Split staged edits across features: "
                + ", ".join(sorted(features)),
            }
        )
    return results


if __name__ == "__main__":
    print(json.dumps(findings(Path(sys.argv[1]) if len(sys.argv) > 1 else Path.cwd())))
