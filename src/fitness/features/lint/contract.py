from itertools import combinations
from pathlib import Path
from typing import cast

import yaml

from fitness.contracts import Document, FitnessError, FitnessFunction, FitnessFunctions
from fitness.features.lint.loading import UniqueLoader


def lint_fitness_functions(path: Path) -> FitnessFunctions:
    files = (
        sorted(p for p in path.rglob("*") if p.suffix in {".yaml", ".yml"} and p.is_file())
        if path.is_dir()
        else [path]
    )
    if not files:
        raise FitnessError(f"{path}: no YAML definitions found")
    tools = {}
    fitness_functions = []
    for file in files:
        try:
            text = file.read_text()
            document = Document.model_validate(yaml.load(text, Loader=UniqueLoader))
            node = cast(yaml.MappingNode, yaml.compose(text))
            lines: list[int] = []
            for key, value in node.value:
                if key.value == "functions":
                    lines = [item.start_mark.line + 1 for item in value.value]
            for name, tool in document.tools.items():
                if name in tools:
                    raise FitnessError(f"duplicate tool {name!r}")
                tools[name] = tool
            fitness_functions.extend(
                FitnessFunction(function=function, source=f"{file}:{line}")
                for function, line in zip(document.functions, lines, strict=True)
            )
        except (OSError, ValueError, yaml.YAMLError, FitnessError) as error:
            raise FitnessError(f"{file}: {error}") from error
    for fitness_function in fitness_functions:
        function = fitness_function.function
        if function.tool and function.tool not in tools:
            raise FitnessError(f"{fitness_function.source}: unknown tool {function.tool!r}")
    warnings = []
    for name in tools:
        automated = [f for f in fitness_functions if f.function.tool == name]
        for left, right in combinations(automated, 2):
            a, b = left.function.rules, right.function.rules
            if a is None or b is None or set(a).intersection(b):
                warnings.append(
                    f"{name}: {left.source} and {right.source} overlap; "
                    "shared findings count toward each function"
                )
    return FitnessFunctions(tools=tools, fitness_functions=fitness_functions, warnings=warnings)
