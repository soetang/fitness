from pathlib import Path

import pytest

from fitness.features.lint.contract import lint_fitness_functions

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture
def definitions_path():
    return FIXTURES / "definitions"


@pytest.fixture
def suite(definitions_path: Path):
    return lint_fitness_functions(definitions_path)


@pytest.fixture
def findings_json():
    return (FIXTURES / "findings.json").read_text()


@pytest.fixture
def write_definitions(tmp_path: Path):
    def write(text: str):
        path = tmp_path / "functions.yaml"
        path.write_text(text)
        return path

    return write
