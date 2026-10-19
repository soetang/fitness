import json
from pathlib import Path

from syrupy.assertion import SnapshotAssertion
from typer.testing import CliRunner

from fitness.cli import create_app


def test_context_markdown_snapshot(tmp_path: Path, snapshot: SnapshotAssertion):
    path = tmp_path / "definitions.yaml"
    path.write_text(
        "description: Example agent expectations\ncontexts: [startup]\nfunctions:\n"
        "  - title: Keep public interfaces understandable\n"
        "    type: architecture\n    include_in_context: startup\n"
        "    guidance: |\n"
        "      Explain the intent of each public operation.\n\n"
        "      - Use domain language.\n"
        "      - Include an example where it helps.\n"
        "  - title: Prefer focused changes\n"
        "    type: maintainability\n    include_in_context: startup\n"
        "  - title: Keep diagnostics actionable\n"
        "    type: usability\n    include_in_context: startup\n"
        "    guidance: Tell the reader what failed and how to fix it.\n"
    )
    result = CliRunner().invoke(create_app(), ["context", "startup", "--rules", str(path)])
    assert result.exit_code == 0, result.output
    assert result.stdout == snapshot


def test_context_cli_outputs_and_errors_without_adapter_execution(tmp_path: Path):
    path = tmp_path / "definitions.yaml"
    path.write_text(
        "description: Context example\ncontexts: [startup, empty]\n"
        "tools: {unused: {command: [nonexistent-command]}}\nfunctions:\n"
        "  - title: Example\n    type: architecture\n    tool: unused\n"
        "    rules: [X]\n    guidance: Follow this advice.\n    include_in_context: startup\n"
    )
    runner = CliRunner()
    app = create_app()
    args = ["context", "startup", "--rules", str(path)]
    result = runner.invoke(app, args)
    assert result.exit_code == 0, result.output
    assert result.stdout == "## Example\n\nFollow this advice.\n"
    result = runner.invoke(app, [*args, "--json"])
    assert result.exit_code == 0, result.output
    data = json.loads(result.stdout)
    assert data["context"] == "startup"
    assert data["fitness_functions"][0]["function"]["rules"] == ["X"]
    assert data["fitness_functions"][0]["source"] == f"{path}:5"
    for json_args in (list[str](), ["--json"]):
        result = runner.invoke(app, ["context", "empty", "--rules", str(path), *json_args])
        assert result.exit_code == 0
        if json_args:
            assert json.loads(result.stdout)["fitness_functions"] == []
        else:
            assert result.stdout == ""
    result = runner.invoke(app, ["context", "typo", "--rules", str(path)])
    assert result.exit_code == 2
    assert result.stdout == ""
    assert "undeclared context" in result.stderr
