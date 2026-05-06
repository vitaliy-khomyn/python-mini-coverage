import ast

from typing import Set, Optional

from .base import CoverageMetric
from .visitor import BaseVisitor


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


class ReturnVisitor(BaseVisitor):
    def __init__(self, ignored_lines: Set[int]):
        super().__init__(ignored_lines)
        self.return_lines: Set[int] = set()

    def visit_Return(self, node: ast.Return) -> None:
        if not self.is_ignored(node):
            self.return_lines.add(node.lineno)
        self.generic_visit(node)
