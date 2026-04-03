import ast
from typing import Set, Tuple, Optional

from .base import CoverageMetric
from .visitor import NextStatementVisitor


class LoopCoverage(CoverageMetric):
    """
    Loop Coverage Implementation.
    Identifies loops and checks if they were both entered and skipped.
    """

    def get_name(self) -> str:
        return "Loop"

    def get_possible_elements(
        self,
        tree: ast.AST,
        ignored_lines: Optional[Set[int]] = None
    ) -> Set[Tuple[int, int]]:
        """
        Returns a set of expected arcs (from_line, to_line) for loops.
        """
        visitor = LoopVisitor(ignored_lines or set())
        visitor.visit(tree)
        return visitor.arcs


class LoopVisitor(NextStatementVisitor):
    def __init__(self, ignored_lines: Set[int]):
        super().__init__()
        self.ignored_lines = ignored_lines
        self.arcs: Set[Tuple[int, int]] = set()

    def visit_For(self, node: ast.For) -> None:
        if node.lineno not in self.ignored_lines:
            if node.body:
                self.arcs.add((node.lineno, node.body[0].lineno))
            exit_node = node.orelse[0] if node.orelse else self._find_next_statement(node)
            if exit_node:
                self.arcs.add((node.lineno, exit_node.lineno))
        self.generic_visit(node)

    def visit_While(self, node: ast.While) -> None:
        if node.lineno not in self.ignored_lines:
            if node.body:
                self.arcs.add((node.lineno, node.body[0].lineno))
            exit_node = node.orelse[0] if node.orelse else self._find_next_statement(node)
            if exit_node:
                self.arcs.add((node.lineno, exit_node.lineno))
        self.generic_visit(node)
