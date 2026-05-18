import ast

from typing import Set, Tuple, Optional, Any

from .base import CoverageMetric
from .visitor import NextStatementVisitor
from ..engine.trace_data import TraceDataType


class LoopCoverage(CoverageMetric):
    """
    Loop Coverage Implementation.
    Identifies loops and checks if they were both entered and skipped.
    """

    def get_name(self) -> str:
        return "Loop"

    def get_required_dynamic_data(self) -> TraceDataType:
        return TraceDataType.ARCS

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
        super().__init__(ignored_lines)
        self.arcs: Set[Tuple[int, int]] = set()

    def _handle_loop(self, node: Any) -> None:
        if not self.is_ignored(node):
            start = node.lineno
            body_target, exit_target = self._get_loop_targets(node)
            if body_target:
                self.arcs.add((start, body_target.lineno))
            if exit_target:
                self.arcs.add((start, exit_target.lineno))
        self.generic_visit(node)

    def visit_For(self, node: ast.For) -> None:
        self._handle_loop(node)

    def visit_While(self, node: ast.While) -> None:
        self._handle_loop(node)
