import pytest

from fitness.contracts import FitnessError, FitnessFunction, FitnessFunctions, Function
from fitness.features.context.contract import select_context


def test_selection_is_ordered_and_independent_of_type_and_automation():
    entries = [
        FitnessFunction(
            source=f"functions.yaml:{index}",
            function=Function(
                title=title,
                type="architecture",
                include_in_context=contexts,
                guidance=guidance,
                tool="unused",
                rules=["X"],
            ),
        )
        for index, (title, contexts, guidance) in enumerate(
            [
                ("First", ["startup", "python"], "Useful instructions."),
                ("Hidden", list[str](), None),
                ("Last", ["startup"], None),
            ],
            start=1,
        )
    ]
    definitions = FitnessFunctions(
        tools={}, contexts=["startup", "empty"], fitness_functions=entries, warnings=[]
    )
    result = select_context(definitions, "startup")
    assert result.fitness_functions == [entries[0], entries[2]]
    assert result.markdown() == "## First\n\nUseful instructions.\n\n## Last"
    assert result.model_dump()["fitness_functions"][0]["function"]["rules"] == ["X"]
    assert select_context(definitions, "empty").markdown() == ""
    with pytest.raises(FitnessError, match="undeclared context"):
        select_context(definitions, "Startup")
