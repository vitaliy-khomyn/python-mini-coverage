import ast

from typing import Set, Tuple, Optional, Dict, Any

from .visitor import BaseVisitor
from .base import CoverageMetric

# tuple stores: (callable_name, line_no)
CallSiteElement = Tuple[str, int]


class CallSiteCoverage(CoverageMetric):
    """
    Call-Site Coverage Implementation.
    Analyzes if every place where a function is explicitly invoked was executed.
    """

    def get_name(self) -> str:
        return "Call-Site"

    def get_possible_elements(
        self,
        tree: ast.AST,
        ignored_lines: Optional[Set[int]] = None
    ) -> Set[CallSiteElement]:
        """
        Returns a set of tuples representing all function call invocations.
        """
        visitor = CallSiteVisitor(ignored_lines or set())
        visitor.visit(tree)
        return visitor.call_sites

    def calculate_stats(
        self,
        possible_elements: Set[CallSiteElement],
        executed_elements: Set[int]
    ) -> Dict[str, Any]:
        """
        Calculates coverage stats for call sites.
        'executed_elements' for this metric is the set of executed line numbers.
        """
        if not possible_elements:
            return {
                'pct': 100.0, 'missing': set(), 'executed': set(),
                'possible': set(), 'ratio': "0/0"
            }

        covered_elements = {
            call for call in possible_elements if call[1] in executed_elements
        }
        missing_elements = possible_elements - covered_elements

        pct = (len(covered_elements) / len(possible_elements)) * 100 if possible_elements else 100.0
        ratio = f"{len(covered_elements)}/{len(possible_elements)}"

        return {
            'pct': pct,
            'missing': missing_elements,
            'executed': covered_elements,
            'possible': possible_elements,
            'ratio': ratio
        }


class CallSiteVisitor(BaseVisitor):
    def __init__(self, ignored_lines: Set[int]):
        super().__init__(ignored_lines)
        self.call_sites: Set[CallSiteElement] = set()

    def visit_Call(self, node: ast.Call) -> None:
        if not self.is_ignored(node):
            name = self._get_name(node.func)
            self.call_sites.add((name, node.lineno))
        self.generic_visit(node)

    def _get_name(self, node: ast.AST) -> str:
        if isinstance(node, ast.Name):
            return node.id
        elif isinstance(node, ast.Attribute):
            return node.attr
        return "<callable>"
