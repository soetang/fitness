import json
import subprocess
import sys
from collections.abc import Callable
from pathlib import Path
from types import ModuleType
from typing import cast

import pytest
from pydantic import JsonValue

RunConfiguredAdapter = Callable[[Path, dict[str, JsonValue]], subprocess.CompletedProcess[str]]
Findings = Callable[[Path], list[dict[str, str]]]
TokenFindings = Callable[[Path, int, str], list[dict[str, str]]]


def architecture_results(
    root: Path, rule: str, config: dict[str, JsonValue] | None = None
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(Path(__file__).with_name("adapter.py")), str(root)],
        input=json.dumps({"selections": [{"rules": [rule], "config": config or {}}]}),
        text=True,
        capture_output=True,
        check=False,
    )


@pytest.fixture
def findings(adapter_module: ModuleType) -> Findings:
    return cast(Findings, adapter_module.findings)


@pytest.fixture
def token_findings(adapter_module: ModuleType) -> TokenFindings:
    return cast(TokenFindings, adapter_module.token_findings)


def test_reports_each_misplaced_adapter_test(tmp_path: Path, findings: Findings):
    tests = tmp_path / "tests" / "nested"
    tests.mkdir(parents=True)
    for name in ("test_adapters.py", "test_ruff_adapter.py", "test_fitness.py"):
        (tests / name).touch()
    result = findings(tmp_path)
    assert [item["filename"] for item in result] == [
        "tests/nested/test_adapters.py",
        "tests/nested/test_ruff_adapter.py",
    ]
    assert all(item["rule_id"] == "adapter-test-location" for item in result)


def test_adapter_tests_in_tool_are_allowed(tmp_path: Path, findings: Findings):
    tool = tmp_path / "fitness" / "tool" / "example"
    tool.mkdir(parents=True)
    (tool / "adapter.py").touch()
    (tool / "test_adapter.py").touch()
    assert findings(tmp_path) == []


@pytest.mark.parametrize(
    "configuration",
    ["[tool.ruff]\n", "[tool.ruff]\nline-length = 100\n", '[tool.ruff.lint]\nselect = ["F"]\n'],
)
def test_rejects_ruff_configuration_in_pyproject(
    tmp_path: Path, configuration: str, findings: Findings
):
    (tmp_path / "pyproject.toml").write_text(configuration)
    result = findings(tmp_path)
    assert len(result) == 1
    assert result[0]["rule_id"] == "ruff-config-location"
    assert result[0]["filename"] == "pyproject.toml"


def test_allows_other_native_configuration(tmp_path: Path, findings: Findings):
    (tmp_path / "pyproject.toml").write_text('[tool.pyrefly]\npython-version = "3.11"\n')
    assert findings(tmp_path) == []


def test_rejects_direct_ruff_checks_in_justfile(tmp_path: Path, findings: Findings):
    (tmp_path / "justfile").write_text("lint:\n    uv run ruff check .\n    ruff check --fix .\n")
    result = findings(tmp_path)
    assert len(result) == 2
    assert all(item["rule_id"] == "fitness-owns-ruff-check" for item in result)
    assert all(item["filename"] == "justfile" for item in result)


def test_allows_fitness_and_formatting_recipes(tmp_path: Path, findings: Findings):
    (tmp_path / "justfile").write_text(
        "# ruff check belongs in the adapter\n"
        "fmt:\n    uv run ruff format .\n"
        "fitness:\n    # Do not run ruff check here\n    .fitness-runner/bin/fitness check\n"
    )
    assert findings(tmp_path) == []


def test_requires_adapter_folder_and_colocated_tests(tmp_path: Path, findings: Findings):
    tool = tmp_path / "fitness" / "tool"
    tool.mkdir(parents=True)
    (tool / "legacy_adapter.py").touch()
    (tool / "test_orphan.py").touch()
    lonely = tool / "lonely"
    lonely.mkdir()
    (lonely / "adapter.py").touch()
    result = findings(tmp_path)
    assert {(item["filename"], item["rule_id"]) for item in result} == {
        ("fitness/tool/test_orphan.py", "adapter-test-location"),
        ("fitness/tool/legacy_adapter.py", "adapter-folder"),
        ("fitness/tool/lonely/adapter.py", "adapter-folder"),
    }


def test_document_filenames_do_not_restrict_function_types(tmp_path: Path, findings: Findings):
    rules = tmp_path / "fitness" / "functions"
    rules.mkdir(parents=True)
    (rules / "architecture.yaml").write_text("""
description: Expectations for a subject spanning several types.
functions:
  - {title: Structure, type: architecture}
  - {title: Quality, type: lint}
  - {title: Typing, type: typing}
""")
    assert findings(tmp_path) == []


FORBIDDEN_IMPORTS = [
    "import fitness.features.orders.execution",
    "import fitness.features.orders.execution  # nosemgrep",
    "import fitness.features.orders.execution as private",
    "from fitness.features.orders import execution",
    "from fitness.features.orders.execution import execute",
    "from fitness.features.orders.execution import *",
    "from fitness.features.orders import *",
    "from fitness.features import orders",
    "from ..orders.execution import execute",
    "from importlib import import_module as load\nload('fitness.features.orders.execution')",
    "import importlib\nimportlib.import_module('.execution', 'fitness.features.orders')",
    "__import__('fitness.features.orders.execution')",
    "import fitness\nfitness.features.orders.execution.execute()",
    "import fitness as f\nf.features.orders.execution.execute()",
    "import importlib\nimportlib.import_module(name='fitness.features.orders.execution')",
    "__import__(name='fitness.features.orders.execution')",
    "from importlib import import_module as load\n"
    "load(name='.execution', package='fitness.features.orders')",
]
ALLOWED_IMPORTS = [
    "from fitness.features.orders.contract import get_order",
    "from fitness.features.orders import contract",
    "import fitness.features.orders.contract as orders\norders.get_order()",
    "import fitness.features.orders.contract\nfitness.features.orders.contract.get_order()",
    "from .execution import execute",
    "from fitness.contracts import Finding",
    "def run(fitness):\n    return fitness.features.orders.execution()",
    "import fitness\ndef run(fitness):\n    return fitness.features.orders.execution()",
    "import fitness as f\ndef run(f):\n    return f.features.orders.execution()",
    "import fitness\nfitness = object()\nfitness.features.orders.execution()",
]
EXTERNAL_CALLERS = [
    "src/fitness/contracts/__init__.py",
    "src/fitness/contracts/domain.py",
    "tests/features/orders/test_execution.py",
    "tool/example.py",
    "example.py",
]


@pytest.fixture(scope="module")
def contract_violations(tmp_path_factory: pytest.TempPathFactory) -> list[dict[str, str]]:
    """One real scan covers independent import examples in separate files."""
    root = tmp_path_factory.mktemp("contract-access")
    examples = {
        f"src/fitness/features/client/{group}_{index}.py": statement
        for group, statements in (("forbidden", FORBIDDEN_IMPORTS), ("allowed", ALLOWED_IMPORTS))
        for index, statement in enumerate(statements)
    }
    for name in EXTERNAL_CALLERS:
        module = "contract" if "contracts/" in name else "execution"
        examples[name] = f"from fitness.features.orders.{module} import execute"
    for name, statement in examples.items():
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(statement, encoding="utf-8")
    (root / "pyproject.toml").write_text('[project]\ndependencies = ["unused"]\n')
    result = subprocess.run(
        [sys.executable, str(Path(__file__).with_name("adapter.py")), str(root)],
        input=json.dumps(
            {
                "selections": [
                    {"rules": ["contract-only-feature-access"]},
                    {
                        "rules": ["feature-token-budget"],
                        "config": {"budget": 1, "encoding": "cl100k_base"},
                    },
                    {
                        "rules": ["dependency-placement"],
                        "config": {"module_mapping": {"unused": ["unused"]}},
                    },
                ]
            }
        ),
        text=True,
        capture_output=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout)


@pytest.mark.xdist_group("layout_imports")
def test_combined_import_checks(contract_violations: list[dict[str, str]]):
    dependencies = [f for f in contract_violations if f["rule_id"] == "dependency-placement"]
    assert len(dependencies) == 1
    assert dependencies[0]["filename"] == "pyproject.toml"
    assert "unused" in dependencies[0]["tool_message"]
    budgets = [f for f in contract_violations if f["rule_id"] == "feature-token-budget"]
    assert len(budgets) == 1
    assert budgets[0]["filename"] == "src/fitness/features/client"


@pytest.mark.parametrize("index", range(len(FORBIDDEN_IMPORTS)), ids=FORBIDDEN_IMPORTS)
@pytest.mark.xdist_group("layout_imports")
def test_rejects_contract_bypasses(contract_violations: list[dict[str, str]], index: int):
    violations = [
        finding
        for finding in contract_violations
        if finding["filename"] == f"src/fitness/features/client/forbidden_{index}.py"
    ]
    assert violations
    assert all(f["rule_id"] == "contract-only-feature-access" for f in violations)


@pytest.mark.parametrize("index", range(len(ALLOWED_IMPORTS)), ids=ALLOWED_IMPORTS)
@pytest.mark.xdist_group("layout_imports")
def test_allows_contracts_and_own_implementation(
    contract_violations: list[dict[str, str]], index: int
):
    assert not any(
        finding["filename"] == f"src/fitness/features/client/allowed_{index}.py"
        for finding in contract_violations
    )


@pytest.mark.parametrize("path", EXTERNAL_CALLERS)
@pytest.mark.xdist_group("layout_imports")
def test_enforces_external_callers_and_shared_dependency_direction(
    contract_violations: list[dict[str, str]], path: str
):
    assert len([f for f in contract_violations if f["filename"] == path]) == 1


def test_combined_token_budget_and_deterministic_file_policy(
    tmp_path: Path, write_file: Callable[[str, str], Path], token_findings: TokenFindings
):
    text = "hello world\r\n<|endoftext|>\n"
    included = [
        "src/fitness/features/orders/contract.py",
        "src/fitness/features/orders/execution.py",
        "src/fitness/features/orders/nested/helpers.py",
    ]
    for name in included:
        write_file(name, text)
    for name in [
        "src/fitness/features/orders/.hidden.txt",
        "src/fitness/features/orders/__pycache__/cached.py",
        "src/fitness/features/orders/image.bin",
        "src/fitness/contracts/shared.py",
        "tests/features/orders/test_orders.py",
        "docs/features/orders/design.md",
        "tests/test_cli.py",
        "tests/conftest.py",
        "tests/fixtures/findings.json",
        "tests/unassociated.txt",
    ]:
        write_file(name, text * 100)
    # Fixed cl100k_base fixture: hello, ' world', CRLF, <, |, endo, ft, ext, |, >LF.
    # Three source files, ten ordinary-text tokens each (including special-token text).
    count = 30
    assert token_findings(tmp_path, count, "cl100k_base") == []
    violations = token_findings(tmp_path, count - 1, "cl100k_base")
    assert len(violations) == 1
    assert f"{count} tokens" in violations[0]["tool_message"]


@pytest.mark.parametrize(
    ("config", "diagnostic"),
    [
        ({"budget": 10, "encoding": "missing"}, "Unknown encoding missing"),
        (
            {"budget": 10, "encoding": "cl100k_base", "associated_files": {"missing": []}},
            "extra_forbidden",
        ),
        ({"budget": 10, "encoding": "cl100k_base", "extra": True}, "extra_forbidden"),
    ],
)
def test_invalid_token_configuration_is_an_error(
    tmp_path: Path,
    write_file: Callable[[str, str], Path],
    config: dict[str, JsonValue],
    diagnostic: str,
):
    write_file("src/fitness/features/orders/contract.py", "")
    result = architecture_results(tmp_path, "feature-token-budget", config)
    assert result.returncode != 0
    assert diagnostic in result.stderr
    assert result.stdout == ""


def test_dependency_mapping_typing_extras_markers_and_build_requirements(
    tmp_path: Path, write_file: Callable[[str, str], Path]
):
    write_file(
        "pyproject.toml",
        """
[project]
dependencies = ["PyYAML>=6", "unused[extra]>=1; python_version >= '3.11'", "hatchling"]
[project.optional-dependencies]
types = ["typing-extensions>=4"]
[build-system]
requires = ["hatchling"]
[dependency-groups]
dev = ["pytest", "tiktoken"]
""",
    )
    write_file(
        "src/example.py",
        "import importlib\nimportlib.import_module(name='yaml')\n"
        "if TYPE_CHECKING:\n    import typing_extensions\n",
    )
    write_file("tests/test_example.py", "import unused\n")
    result = architecture_results(
        tmp_path,
        "dependency-placement",
        {
            "module_mapping": {
                "pyyaml": ["yaml"],
                "unused": ["unused"],
                "hatchling": ["hatchling"],
                "typing_extensions": ["typing_extensions"],
            },
        },
    )
    assert result.returncode == 0, result.stderr
    violations = json.loads(result.stdout)
    assert len(violations) == 2
    assert any(
        "hatchling" in f["tool_message"] and "build-system.requires" in f["tool_message"]
        for f in violations
    )
    assert any(
        "unused" in f["tool_message"] and "dev group" in f["tool_message"] for f in violations
    )


def test_unknown_distribution_requires_mapping(
    tmp_path: Path, write_file: Callable[[str, str], Path]
):
    write_file("pyproject.toml", '[project]\ndependencies = ["unmapped"]\n')
    result = architecture_results(tmp_path, "dependency-placement", {"module_mapping": {}})
    assert result.returncode != 0
    assert "No explicit distribution/import mapping" in result.stderr
    assert result.stdout == ""


@pytest.mark.parametrize(
    ("payload", "diagnostic"),
    [
        ({"config": {"unknown": True}}, "too_long"),
        ({"selections": [{"rules": None}]}, "Layout selections require explicit rule IDs"),
        ({"selections": [{"rules": ["unknown"]}]}, "Unsupported layout rule: unknown"),
        (
            {
                "selections": [
                    {"rules": ["contract-only-feature-access"], "config": {"unknown": True}}
                ]
            },
            "extra_forbidden",
        ),
        (
            {
                "selections": [
                    {
                        "rules": ["feature-token-budget"],
                        "config": {"budget": 100, "encoding": "cl100k_base"},
                    },
                    {
                        "rules": ["feature-token-budget"],
                        "config": {"budget": 200, "encoding": "cl100k_base"},
                    },
                ]
            },
            "Conflicting configuration for feature-token-budget",
        ),
    ],
)
def test_invalid_requests_report_the_intended_error(
    tmp_path: Path,
    run_configured_adapter: RunConfiguredAdapter,
    payload: dict[str, JsonValue],
    diagnostic: str,
):
    result = run_configured_adapter(tmp_path, payload)
    assert result.returncode != 0
    assert diagnostic in result.stderr
    assert result.stdout == ""


def test_only_selected_architecture_checks_execute(
    tmp_path: Path,
    write_file: Callable[[str, str], Path],
    run_configured_adapter: RunConfiguredAdapter,
):
    write_file("pyproject.toml", '[project]\ndependencies = ["no-mapping"]\n')
    write_file("src/client.py", "import fitness.features.orders.execution\n")
    result = run_configured_adapter(
        tmp_path,
        {
            "selections": [{"rules": ["contract-only-feature-access"]}],
        },
    )
    assert result.returncode == 0, result.stderr
    assert [f["rule_id"] for f in json.loads(result.stdout)] == ["contract-only-feature-access"]


def test_token_budget_does_not_follow_symlinks(
    tmp_path: Path, write_file: Callable[[str, str], Path], token_findings: TokenFindings
):
    write_file("src/fitness/features/orders/contract.py", "pass")
    external = write_file("external/large.txt", "hello world\n" * 1000)
    (tmp_path / "src/fitness/features/orders/linked.txt").symlink_to(external)
    (tmp_path / "src/fitness/features/orders/linked").symlink_to(
        external.parent, target_is_directory=True
    )
    assert token_findings(tmp_path, 1, "cl100k_base") == []


def test_invalid_python_is_an_evaluation_error(
    tmp_path: Path,
    write_file: Callable[[str, str], Path],
    run_configured_adapter: RunConfiguredAdapter,
):
    write_file("src/broken.py", "def invalid syntax")
    result = run_configured_adapter(
        tmp_path,
        {
            "selections": [
                {"rules": ["contract-only-feature-access"]},
                {"rules": ["dependency-placement"], "config": {"module_mapping": {}}},
            ]
        },
    )
    assert result.returncode != 0
    assert "PartialParsing" in result.stderr
    assert result.stdout == ""


def test_later_failure_discards_existing_findings(
    tmp_path: Path,
    write_file: Callable[[str, str], Path],
    run_configured_adapter: RunConfiguredAdapter,
):
    write_file("src/client.py", "import fitness.features.orders.execution\n")
    selection: JsonValue = {"rules": ["contract-only-feature-access"]}
    control = run_configured_adapter(tmp_path, {"selections": [selection]})
    assert control.returncode == 0, control.stderr
    assert [f["rule_id"] for f in json.loads(control.stdout)] == ["contract-only-feature-access"]
    failed = run_configured_adapter(
        tmp_path,
        {
            "selections": [selection, {"rules": ["unknown"]}],
        },
    )
    assert failed.returncode != 0
    assert "Unsupported layout rule: unknown" in failed.stderr
    assert failed.stdout == ""


def test_relative_repository_path_matches_absolute_path(
    tmp_path: Path,
    write_file: Callable[[str, str], Path],
):
    write_file("src/client.py", "import fitness.features.orders.execution\n")
    absolute = architecture_results(tmp_path, "contract-only-feature-access")
    relative = subprocess.run(
        [sys.executable, str(Path(__file__).with_name("adapter.py")), tmp_path.name],
        cwd=tmp_path.parent,
        text=True,
        capture_output=True,
        check=False,
        input=json.dumps({"selections": [{"rules": ["contract-only-feature-access"]}]}),
    )
    assert absolute.returncode == relative.returncode == 0, relative.stderr
    assert relative.stdout == absolute.stdout
    assert json.loads(relative.stdout)[0]["rule_id"] == "contract-only-feature-access"
