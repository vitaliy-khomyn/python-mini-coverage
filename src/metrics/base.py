from typing import Set, Dict, Any


class CoverageMetric:
    """
    Abstract base class for coverage measurement strategies.
    """

    def get_name(self) -> str:
        """
        Return the display name of the metric.
        """
        raise NotImplementedError

    def get_possible_elements(self, source: Any, ignored_lines: Set[int]) -> Set[Any]:
        """
        Analyze the source (AST or Code Object) to determine all possible coverage targets.

        Args:
            source (Any): The parsed source tree (ast.Module) or compiled code object.
            ignored_lines (set): Set of line numbers marked with pragmas to ignore.

        Returns:
            set: A collection of elements (lines, arcs, or conditions) that should be covered.
        """
        raise NotImplementedError

    def calculate_stats(self, possible_elements: Set[Any], executed_data: Set[Any]) -> Dict[str, Any]:
        """
        Compare possible elements against executed data to calculate coverage.

        Args:
            possible_elements (set): The set of static elements found by analysis.
            executed_data (set): The set of dynamic elements collected during execution.

        Returns:
            dict: Statistics including 'pct' (float), 'missing' (set), 'executed' (set).
        """
        if not possible_elements:
            return {
                'pct': 100.0,
                'missing': set(),
                'executed': set(),
                'possible': set()
            }

        hit = possible_elements.intersection(executed_data)
        missing = possible_elements - hit
        pct = (len(hit) / len(possible_elements)) * 100

        return {
            'pct': pct,
            'missing': missing,
            'executed': hit,
            'possible': possible_elements
        }
