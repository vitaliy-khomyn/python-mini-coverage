import ast
from typing import Set, Optional

from .base import CoverageMetric


class ReturnCoverage(CoverageMetric):
    """
    Return Coverage Implementation.
    Analyzes if every explicit `return` statement in the code was executed.
    """

    def get_name(self) -> str:
        return "Return"

    def get_possible_elements(
        self,
        tree: ast.AST,
        ignored_lines: Optional[Set[int]] = None
    ) -> Set[int]:
        visitor = ReturnVisitor(ignored_lines or set())
        visitor.visit(tree)
        return visitor.return_lines


class ReturnVisitor(ast.NodeVisitor):
    def __init__(self, ignored_lines: Set[int]):
        self.ignored_lines = ignored_lines
        self.return_lines: Set[int] = set()

    def visit_Return(self, node: ast.Return) -> None:
        if hasattr(node, 'lineno') and node.lineno not in self.ignored_lines:
            self.return_lines.add(node.lineno)
        self.generic_visit(node)
