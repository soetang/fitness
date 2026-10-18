from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, JsonValue, StringConstraints, model_validator

Text = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]
Count = Annotated[int, Field(strict=True, ge=0)]
Positive = Annotated[int, Field(strict=True, ge=1)]


class Model(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class Tool(Model):
    command: list[Text] = Field(min_length=1)
    config: dict[str, JsonValue] = Field(default_factory=dict)
    send_input: bool = False


class Function(Model):
    title: Text
    type: Text
    tool: Text | None = None
    rules: list[Text] | None = Field(default=None, min_length=1)
    guidance: Text | None = None
    limit: Count = 0
    config: dict[str, JsonValue] = Field(default_factory=dict)

    @model_validator(mode="after")
    def references(self):
        if not self.tool and (self.rules or self.config):
            raise ValueError("rules and config require a tool")
        if self.rules is not None and len(self.rules) != len(set(self.rules)):
            raise ValueError("duplicate rule IDs in a function")
        return self


class Document(Model):
    description: Text
    tools: dict[Text, Tool] = Field(default_factory=dict)
    functions: list[Function] = Field(default_factory=list)


class Location(Model):
    row: Positive
    column: Positive


class Finding(Model):
    tool: Text
    rule_id: Text
    tool_message: Text
    filename: Text | None = None
    location: Location | None = None


class FitnessError(Exception):
    pass


class FitnessFunction(Model):
    function: Function
    source: str


class FitnessFunctions(Model):
    tools: dict[str, Tool]
    fitness_functions: list[FitnessFunction]
    warnings: list[str]
