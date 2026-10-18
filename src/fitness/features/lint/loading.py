import yaml

from fitness.contracts import FitnessError


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
