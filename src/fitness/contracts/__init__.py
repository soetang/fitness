"""Define shared validation models and errors for fitness features."""

from typing import Annotated

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    JsonValue,
    StringConstraints,
    field_validator,
    model_validator,
)

Text = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]
Count = Annotated[int, Field(strict=True, ge=0)]
Positive = Annotated[int, Field(strict=True, ge=1)]


class Model(BaseModel):
    """Validate values strictly and reject undeclared fields."""

    model_config = ConfigDict(extra="forbid", strict=True)


class Tool(Model):
    """Configure an adapter command, shared settings, and request transport."""

    command: list[Text] = Field(min_length=1)
    config: dict[str, JsonValue] = Field(default_factory=dict)
    send_input: bool = False


class Function(Model):
    """Describe an expectation with optional automation and a violation limit."""

    title: Text
    type: Text
    tool: Text | None = None
    rules: list[Text] | None = Field(default=None, min_length=1)
    guidance: Text | None = None
    include_in_context: list[Text] = Field(default_factory=list)
    limit: Count = 0
    config: dict[str, JsonValue] = Field(default_factory=dict)

    @field_validator("include_in_context", mode="before")
    @classmethod
    def normalize_contexts(cls, value: object) -> object:
        """Accept a single context name as shorthand for a list.

        Args:
            value: Raw context membership from a definition.
        """
        return [value] if isinstance(value, str) else value

    @model_validator(mode="after")
    def references(self):
        """Reject tool-dependent settings without a tool and duplicate rule IDs."""
        if not self.tool and (self.rules or self.config):
            raise ValueError("rules and config require a tool")
        if self.rules is not None and len(self.rules) != len(set(self.rules)):
            raise ValueError("duplicate rule IDs in a function")
        return self


class Document(Model):
    """Represent a described YAML document containing tools and functions."""

    description: Text
    contexts: list[Text] = Field(default_factory=list)
    tools: dict[Text, Tool] = Field(default_factory=dict)
    functions: list[Function] = Field(default_factory=list)


class Location(Model):
    """Identify a one-based row and column in a diagnostic's source file."""

    row: Positive
    column: Positive


class Finding(Model):
    """Represent one adapter diagnostic and its optional source location."""

    tool: Text
    rule_id: Text
    tool_message: Text
    filename: Text | None = None
    location: Location | None = None


class FitnessError(Exception):
    """Signal a definition or execution failure suitable for user-facing output."""

    pass


class FitnessFunction(Model):
    """Pair a function definition with its diagnostic source reference."""

    function: Function
    source: str


class FitnessFunctions(Model):
    """Collect validated tools, source-located functions, and lint warnings."""

    tools: dict[str, Tool]
    contexts: list[str] = Field(default_factory=list)
    fitness_functions: list[FitnessFunction]
    warnings: list[str]
