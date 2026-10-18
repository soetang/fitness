"""Translate configured Ruff diagnostics into individual Fitness findings."""

import json
import subprocess
import sys

from pydantic import JsonValue


def overrides(config: dict[str, JsonValue], prefix: tuple[str, ...] = ()) -> dict[str, str]:
    """Encode native settings as Ruff's TOML key/value command-line overrides."""
    result: dict[str, str] = {}
    for key, value in config.items():
        path = (*prefix, key)
        if isinstance(value, dict):
            result.update(overrides(value, path))
        else:
            result[".".join(json.dumps(part) for part in path)] = json.dumps(value)
    return result


def _configuration_flags(
    config: dict[str, JsonValue], function_configs: list[dict[str, JsonValue]]
) -> list[str]:
    """Merge compatible settings before encoding Ruff's configuration override."""
    settings = overrides(config)
    for function_config in function_configs:
        for key, value in overrides(function_config, ("lint",)).items():
            if key in settings and settings[key] != value:
                raise ValueError(
                    f"Conflicting Ruff settings for {key}; split incompatible selections"
                )
            settings[key] = value
    if not settings:
        return []
    return ["--config", "\n".join(f"{key} = {value}" for key, value in settings.items())]


def _selection_flags(rules: list[str], selections: list[list[str] | None]) -> list[str]:
    """Retain native defaults when any function selects the whole tool."""
    if not rules:
        return []
    flag = "--extend-select" if None in selections else "--select"
    return [flag, ",".join(rules)]


def _normalize_findings(
    result: subprocess.CompletedProcess[str], rules: list[str]
) -> list[dict[str, JsonValue]]:
    """Translate native diagnostics while preserving process failures and selectors."""
    if result.returncode not in (0, 1):
        sys.stderr.write(result.stderr)
        raise SystemExit(result.returncode)
    findings = [
        {
            "tool": "ruff",
            "rule_id": max(
                (rule for rule in rules if rule == "ALL" or item["code"].startswith(rule)),
                key=lambda rule: 0 if rule == "ALL" else len(rule),
                default=item["code"],
            ),
            "tool_message": f"{item['code']}: {item['message']}",
            "filename": item["filename"],
            "location": item["location"],
        }
        for item in json.loads(result.stdout)
    ]
    if result.returncode and not findings:
        sys.stderr.write(result.stderr or "Ruff failed without diagnostics\n")
        raise SystemExit(2)
    return findings


def main() -> None:
    request = json.load(sys.stdin)
    selections = request["selections"]
    rules = sorted({rule for item in selections for rule in item["rules"] or []})
    flags = _selection_flags(rules, [item["rules"] for item in selections])
    flags.extend(_configuration_flags(request["config"], [item["config"] for item in selections]))
    result = subprocess.run(
        ["ruff", "check", "--output-format", "json", *flags, *(sys.argv[1:] or ["."])],
        capture_output=True,
        text=True,
        check=False,
    )
    print(json.dumps(_normalize_findings(result, rules)))


if __name__ == "__main__":
    main()
