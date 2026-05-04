import ast
from typing import Set, Optional

from .visitor import BaseVisitor
from .base import CoverageMetric


class ExceptionCoverage(CoverageMetric):
    """
    Exception Coverage Implementation.
    Analyzes if every `except` block in the code was executed.
    """

    def get_name(self) -> str:
        return "Exception"

    def get_possible_elements(
        self,
        tree: ast.AST,
        ignored_lines: Optional[Set[int]] = None
    ) -> Set[int]:
        visitor = ExceptionVisitor(ignored_lines or set())
        visitor.visit(tree)
        return visitor.except_lines


class ExceptionVisitor(BaseVisitor):
    def __init__(self, ignored_lines: Set[int]):
        super().__init__(ignored_lines)
        self.except_lines: Set[int] = set()

    def visit_ExceptHandler(self, node: ast.ExceptHandler) -> None:
        if not self.is_ignored(node):
            self.except_lines.add(node.lineno)
        self.generic_visit(node)
