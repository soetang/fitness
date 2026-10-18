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
    if definitions and implementation:
        return [
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
    return []


if __name__ == "__main__":
    print(json.dumps(findings(Path(sys.argv[1]) if len(sys.argv) > 1 else Path.cwd())))
