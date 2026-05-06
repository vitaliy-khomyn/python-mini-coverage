from abc import ABC
from typing import Set, Dict, Any, Callable, Optional
from ..engine.trace_data import TraceDataType
from enum import Enum


class StaticSourceType(str, Enum):
    AST = 'ast'
    CODE_OBJECT = 'code_object'


class CoverageMetric(ABC):
    """
    Abstract base class for coverage measurement strategies.
    """

    def get_name(self) -> str:
        """
        Return the display name of the metric.
        """
        raise NotImplementedError

    def get_required_static_source(self) -> StaticSourceType:
        """Return 'ast' or 'code_object' to specify static analysis input."""
        return StaticSourceType.AST

    def get_required_dynamic_data(self) -> TraceDataType:
        """
        Return the key for the dynamic data this metric needs,
        e.g., 'lines', 'arcs', 'instruction_arcs'.
        """
        # Default for Statement and Function coverage
        return TraceDataType.LINES

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

    def calculate_stats(self, possible_elements: Set[Any], executed_data: Set[Any], key: Optional[Callable[[Any], Any]] = None) -> Dict[str, Any]:
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
                'possible': set(),
                'ratio': "0/0"
            }

        if key:
            hit = {el for el in possible_elements if key(el) in executed_data}
        else:
            hit = possible_elements.intersection(executed_data)

        missing = possible_elements - hit
        pct = (len(hit) / len(possible_elements)) * 100
        ratio = f"{len(hit)}/{len(possible_elements)}"

        return {
            'pct': pct,
            'missing': missing,
            'executed': hit,
            'possible': possible_elements,
            'ratio': ratio
        }
