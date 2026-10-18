"""Report misplaced adapter test modules using the project's naming convention."""

import json
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
    return results


if __name__ == "__main__":
    print(json.dumps(findings(Path.cwd())))
