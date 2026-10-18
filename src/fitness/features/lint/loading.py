from pathlib import Path
from typing import cast

import yaml

from fitness.contracts import Document, FitnessError, FitnessFunction, Tool


class UniqueLoader(yaml.SafeLoader):
    """Reject duplicate YAML keys instead of silently overwriting definitions."""

    def construct_mapping(self, node: yaml.MappingNode, deep: bool = False):
        keys = [self.construct_object(key, deep=deep) for key, _ in node.value]
        try:
            if len(keys) != len(set(keys)):
                raise FitnessError(f"duplicate YAML key at line {node.start_mark.line + 1}")
        except TypeError as error:
            raise FitnessError("YAML mapping keys must be scalar") from error
        return super().construct_mapping(node, deep=deep)


def find_fitness_documents(path: Path) -> list[Path]:
    files = (
        sorted(p for p in path.rglob("*") if p.suffix in {".yaml", ".yml"} and p.is_file())
        if path.is_dir()
        else [path]
    )
    if not files:
        raise FitnessError(f"{path}: no YAML definitions found")
    return files


def read_fitness_document(file: Path) -> tuple[Document, list[int]]:
    text = file.read_text()
    document = Document.model_validate(yaml.load(text, Loader=UniqueLoader))
    node = cast(yaml.MappingNode, yaml.compose(text))
    lines: list[int] = []
    for key, value in node.value:
        if key.value == "functions":
            lines = [item.start_mark.line + 1 for item in value.value]
    return document, lines


def register_document_tools(tools: dict[str, Tool], document: Document) -> None:
    for name, tool in document.tools.items():
        if name in tools:
            raise FitnessError(f"duplicate tool {name!r}")
        tools[name] = tool


def load_fitness_functions(path: Path) -> tuple[dict[str, Tool], list[FitnessFunction]]:
    tools: dict[str, Tool] = {}
    fitness_functions = []
    for file in find_fitness_documents(path):
        try:
            document, lines = read_fitness_document(file)
            register_document_tools(tools, document)
            fitness_functions.extend(
                FitnessFunction(function=function, source=f"{file}:{line}")
                for function, line in zip(document.functions, lines, strict=True)
            )
        except (OSError, ValueError, yaml.YAMLError, FitnessError) as error:
            raise FitnessError(f"{file}: {error}") from error
    return tools, fitness_functions
