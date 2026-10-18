import importlib
import json
import subprocess
import sys
from collections.abc import Mapping
from pathlib import Path
from types import MappingProxyType, ModuleType

import pytest
from pydantic import BaseModel, ConfigDict, JsonValue

pytestmark = pytest.mark.xdist_group("layout_imports")

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
    (
        "from importlib import import_module as load\n"
        "load(name='.execution', package='fitness.features.orders')"
    ),
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
COMBINED_REQUEST: dict[str, JsonValue] = {
    "selections": [
        {"rules": ["contract-only-feature-access"]},
        {"rules": ["feature-token-budget"], "config": {"budget": 1, "encoding": "cl100k_base"}},
        {"rules": ["dependency-placement"], "config": {"module_mapping": {"unused": ["unused"]}}},
    ]
}


class ImportCase(BaseModel):
    model_config = ConfigDict(frozen=True, arbitrary_types_allowed=True)

    root: Path
    references: MappingProxyType[Path, tuple[tuple[str, int], ...]]

    def scan(self, root: Path, source_only: bool) -> dict[Path, list[tuple[str, int]]]:
        assert root == self.root
        return {
            path: list(values)
            for path, values in self.references.items()
            if not source_only or path.is_relative_to(root / "src")
        }

    def evaluate(self, adapter: ModuleType, payload: dict[str, JsonValue]) -> list[dict[str, str]]:
        return adapter.findings(
            self.root, adapter.Request.model_validate(payload), scanner=self.scan
        )


@pytest.fixture(scope="module")
def import_cases(
    tmp_path_factory: pytest.TempPathFactory, adapter_module: ModuleType
) -> Mapping[str, ImportCase]:
    """One native manifest, independent roots, no mutations after fact collection."""
    imports = importlib.import_module("imports")  # Loaded by the real adapter fixture.
    contract = {
        f"src/fitness/features/client/{group}_{index}.py": statement
        for group, statements in (("forbidden", FORBIDDEN_IMPORTS), ("allowed", ALLOWED_IMPORTS))
        for index, statement in enumerate(statements)
    }
    for name in EXTERNAL_CALLERS:
        module = "contract" if "contracts/" in name else "execution"
        contract[name] = f"from fitness.features.orders.{module} import execute"
    contract["pyproject.toml"] = '[project]\ndependencies = ["unused"]\n'
    sources = {
        "contract": contract,
        "dependencies": {
            "pyproject.toml": """[project]
dependencies = ["PyYAML>=6", "unused[extra]>=1; python_version >= '3.11'", "hatchling"]
[project.optional-dependencies]
types = ["typing-extensions>=4"]
[build-system]
requires = ["hatchling"]
[dependency-groups]
dev = ["pytest", "tiktoken"]
""",
            "src/example.py": "import importlib\nimportlib.import_module(name='yaml')\n"
            "if TYPE_CHECKING:\n    import typing_extensions\n",
            "tests/test_example.py": "import unused\n",
        },
        "placement": {
            **dict.fromkeys(
                [
                    "tests/features/orders/test_contract.py",
                    "tests/test_orders.py",
                    "tests/features/client/orders_test.py",
                    "tests/conftest.py",
                ],
                "from fitness.features.orders.contract import get_order\n",
            ),
            "tests/test_cli.py": "from fitness.cli import create_app\n",
            "tests/features/orders/test_private.py": (
                "from fitness.features.orders.execution import execute\n"
            ),
        },
        "placement-alone": {
            "tests/test_orders.py": "from fitness.features.orders.contract import get_order\n"
        },
        "selection": {
            "pyproject.toml": '[project]\ndependencies = ["no-mapping"]\n',
            "src/client.py": "import fitness.features.orders.execution\n",
        },
    }
    common = tmp_path_factory.mktemp("import-policy")
    for name, files in sources.items():
        for relative, text in files.items():
            path = common / name / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text, encoding="utf-8")
    paths: list[Path] = imports.python_files(common)
    scan = imports.analyze_python_imports(common, paths)
    cases = {}
    for name in sources:
        root = common / name
        own_paths = [path for path in paths if path.is_relative_to(root)]
        own_scan = scan.model_copy(
            update={
                "results": [
                    match for match in scan.results if Path(match.path).is_relative_to(root)
                ]
            }
        )
        # Resolve relative imports against the individual subject, not the batch root.
        references: dict[Path, list[tuple[str, int]]] = imports.collect_import_references(
            root, own_paths, own_scan
        )
        cases[name] = ImportCase(
            root=root,
            references=MappingProxyType(
                {path: tuple(values) for path, values in references.items()}
            ),
        )
    return MappingProxyType(cases)


@pytest.fixture(scope="module")
def contract_violations(
    import_cases: Mapping[str, ImportCase], adapter_module: ModuleType
) -> list[dict[str, str]]:
    return import_cases["contract"].evaluate(adapter_module, COMBINED_REQUEST)


def test_combined_import_checks(contract_violations: list[dict[str, str]]):
    dependencies = [f for f in contract_violations if f["rule_id"] == "dependency-placement"]
    assert len(dependencies) == 1
    assert dependencies[0]["filename"] == "pyproject.toml"
    assert "unused" in dependencies[0]["tool_message"]
    budgets = [f for f in contract_violations if f["rule_id"] == "feature-token-budget"]
    assert len(budgets) == 1
    assert budgets[0]["filename"] == "src/fitness/features/client"


@pytest.mark.parametrize("index", range(len(FORBIDDEN_IMPORTS)), ids=FORBIDDEN_IMPORTS)
def test_rejects_contract_bypasses(contract_violations: list[dict[str, str]], index: int):
    violations = [
        finding
        for finding in contract_violations
        if finding["filename"] == f"src/fitness/features/client/forbidden_{index}.py"
    ]
    assert violations
    assert all(f["rule_id"] == "contract-only-feature-access" for f in violations)


@pytest.mark.parametrize("index", range(len(ALLOWED_IMPORTS)), ids=ALLOWED_IMPORTS)
def test_allows_contracts_and_own_implementation(
    contract_violations: list[dict[str, str]], index: int
):
    assert not any(
        finding["filename"] == f"src/fitness/features/client/allowed_{index}.py"
        for finding in contract_violations
    )


@pytest.mark.parametrize("path", EXTERNAL_CALLERS)
def test_enforces_external_callers_and_shared_dependency_direction(
    contract_violations: list[dict[str, str]], path: str
):
    assert len([f for f in contract_violations if f["filename"] == path]) == 1


def test_dependency_mapping_typing_extras_markers_and_build_requirements(
    import_cases: Mapping[str, ImportCase], adapter_module: ModuleType
):
    violations = import_cases["dependencies"].evaluate(
        adapter_module,
        {
            "selections": [
                {
                    "rules": ["dependency-placement"],
                    "config": {
                        "module_mapping": {
                            "pyyaml": ["yaml"],
                            "unused": ["unused"],
                            "hatchling": ["hatchling"],
                            "typing_extensions": ["typing_extensions"],
                        }
                    },
                }
            ]
        },
    )
    assert len(violations) == 2
    assert any(
        "hatchling" in f["tool_message"] and "build-system.requires" in f["tool_message"]
        for f in violations
    )
    assert any(
        "unused" in f["tool_message"] and "dev group" in f["tool_message"] for f in violations
    )


def test_only_selected_architecture_checks_execute(
    import_cases: Mapping[str, ImportCase], adapter_module: ModuleType
):
    result = import_cases["selection"].evaluate(
        adapter_module, {"selections": [{"rules": ["contract-only-feature-access"]}]}
    )
    assert [f["rule_id"] for f in result] == ["contract-only-feature-access"]


def test_later_failure_discards_existing_findings(
    import_cases: Mapping[str, ImportCase], adapter_module: ModuleType
):
    case = import_cases["selection"]
    selection: JsonValue = {"rules": ["contract-only-feature-access"]}
    control = case.evaluate(adapter_module, {"selections": [selection]})
    assert [f["rule_id"] for f in control] == ["contract-only-feature-access"]
    failed = subprocess.run(
        [sys.executable, str(Path(__file__).with_name("adapter.py")), str(case.root)],
        input=json.dumps({"selections": [selection, {"rules": ["unknown"]}]}),
        capture_output=True,
        text=True,
        check=False,
    )
    assert failed.returncode != 0
    assert "Unsupported layout rule: unknown" in failed.stderr
    assert failed.stdout == ""


def test_feature_test_placement_and_contract_checks_share_analysis(
    import_cases: Mapping[str, ImportCase], adapter_module: ModuleType
):
    result = import_cases["placement"].evaluate(
        adapter_module,
        {"selections": [{"rules": ["feature-test-location", "contract-only-feature-access"]}]},
    )
    assert {(f["filename"], f["rule_id"]) for f in result} == {
        ("tests/test_orders.py", "feature-test-location"),
        ("tests/features/client/orders_test.py", "feature-test-location"),
        ("tests/features/orders/test_private.py", "contract-only-feature-access"),
    }


def test_placement_check_can_run_on_its_own(
    import_cases: Mapping[str, ImportCase], adapter_module: ModuleType
):
    violations = import_cases["placement-alone"].evaluate(
        adapter_module, {"selections": [{"rules": ["feature-test-location"]}]}
    )
    assert len(violations) == 1
    assert violations[0]["rule_id"] == "feature-test-location"
    assert "tests/features/orders/" in violations[0]["tool_message"]


def test_relative_repository_path_matches_absolute_path(
    import_cases: Mapping[str, ImportCase],
    contract_violations: list[dict[str, str]],
):
    root = import_cases["contract"].root
    relative = subprocess.run(
        [sys.executable, str(Path(__file__).with_name("adapter.py")), root.name],
        cwd=root.parent,
        text=True,
        capture_output=True,
        check=False,
        input=json.dumps(COMBINED_REQUEST),
    )
    assert relative.returncode == 0, relative.stderr
    assert json.loads(relative.stdout) == contract_violations
    assert json.loads(relative.stdout)[0]["rule_id"] == "contract-only-feature-access"
