"""Read YAML definitions while preserving diagnostic source locations."""

from pathlib import Path
from typing import cast

import yaml

from fitness.contracts import Document, FitnessError, FitnessFunction, Tool


class UniqueLoader(yaml.SafeLoader):
    """Reject duplicate YAML keys instead of silently overwriting definitions."""

    def construct_mapping(self, node: yaml.MappingNode, deep: bool = False):
        """Construct a mapping after rejecting duplicate or nonscalar keys.

        Args:
            node: YAML mapping node to construct.
            deep: Whether to construct nested objects eagerly.
        """
        keys = [self.construct_object(key, deep=deep) for key, _ in node.value]
        try:
            if len(keys) != len(set(keys)):
                raise FitnessError(f"duplicate YAML key at line {node.start_mark.line + 1}")
        except TypeError as error:
            raise FitnessError("YAML mapping keys must be scalar") from error
        return super().construct_mapping(node, deep=deep)


def find_fitness_documents(path: Path) -> list[Path]:
    """Find definition files in deterministic order.

    Args:
        path: YAML file or directory to search recursively.
    """
    files = (
        sorted(p for p in path.rglob("*") if p.suffix in {".yaml", ".yml"} and p.is_file())
        if path.is_dir()
        else [path]
    )
    if not files:
        raise FitnessError(f"{path}: no YAML definitions found")
    return files


def read_fitness_document(file: Path) -> tuple[Document, list[int]]:
    """Parse a document and locate each function's starting line.

    Args:
        file: YAML definition file to read.

    Returns:
        Validated document and one-based function line numbers in document order.
    """
    text = file.read_text()
    document = Document.model_validate(yaml.load(text, Loader=UniqueLoader))
    node = cast(yaml.MappingNode, yaml.compose(text))
    lines: list[int] = []
    for key, value in node.value:
        if key.value == "functions":
            lines = [item.start_mark.line + 1 for item in value.value]
    return document, lines


def register_document_tools(tools: dict[str, Tool], document: Document) -> None:
    """Merge document tools into the registry, rejecting duplicate names.

    Args:
        tools: Registry updated in place as tools are encountered.
        document: Validated document supplying tool definitions.
    """
    for name, tool in document.tools.items():
        if name in tools:
            raise FitnessError(f"duplicate tool {name!r}")
        tools[name] = tool


def register_document_definitions(
    tools: dict[str, Tool], contexts: list[str], document: Document
) -> None:
    """Merge named tool and context declarations, rejecting duplicate names.

    Args:
        tools: Tool registry updated in place.
        contexts: Context registry updated in place.
        document: Validated document supplying context names.
    """
    register_document_tools(tools, document)
    for name in document.contexts:
        if name in contexts:
            raise FitnessError(f"duplicate context {name!r}")
        contexts.append(name)


def load_fitness_functions(path: Path) -> tuple[dict[str, Tool], list[FitnessFunction], list[str]]:
    """Collect tools and source-located functions from definition documents.

    Args:
        path: YAML file or directory containing definitions.

    Raises:
        FitnessError: Loading fails, with the failing document identified.
    """
    tools: dict[str, Tool] = {}
    contexts: list[str] = []
    fitness_functions = []
    for file in find_fitness_documents(path):
        try:
            document, lines = read_fitness_document(file)
            register_document_definitions(tools, contexts, document)
            fitness_functions.extend(
                FitnessFunction(function=function, source=f"{file}:{line}")
                for function, line in zip(document.functions, lines, strict=True)
            )
        except (OSError, ValueError, yaml.YAMLError, FitnessError) as error:
            raise FitnessError(f"{file}: {error}") from error
    return tools, fitness_functions, contexts
