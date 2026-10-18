"""Report misplaced adapter test modules using the project's naming convention."""

import json
import re
import tomllib
from pathlib import Path

import yaml


def findings(root: Path) -> list[dict[str, str]]:
    misplaced = list((root / "tests").rglob("test_*adapter*.py"))
    misplaced.extend(
        path
        for path in (root / "fitness" / "tool").rglob("test_*.py")
        if not (path.parent / "adapter.py").is_file()
    )
    results = [
        {
            "tool": "layout",
            "rule_id": "adapter-test-location",
            "tool_message": "Adapter tests belong in fitness/tool/<name>/ beside adapter.py.",
            "filename": str(path.relative_to(root)),
        }
        for path in sorted(misplaced)
        if path.is_file()
    ]
    results.extend(
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
    )
    architecture = root / "fitness" / "functions" / "architecture.yaml"
    if architecture.is_file():
        document = yaml.safe_load(architecture.read_text())
        results.extend(
            {
                "tool": "layout",
                "rule_id": "architecture-function-type",
                "tool_message": f"{function['title']}: expected type architecture.",
                "filename": str(architecture.relative_to(root)),
            }
            for function in document.get("functions", [])
            if function.get("type") != "architecture"
        )
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
    print(json.dumps(findings(Path.cwd())))
