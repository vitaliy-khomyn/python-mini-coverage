import ast
from typing import Set, Tuple, Optional, Any

from .base import CoverageMetric
from .visitor import NextStatementVisitor
from ..engine.trace_data import TraceDataType


class BranchCoverage(CoverageMetric):
    """
    Measures control flow branches (arcs) between lines.
    """

    def get_name(self) -> str:
        return "Branch"

    def get_required_dynamic_data(self) -> TraceDataType:
        return TraceDataType.ARCS

    def get_possible_elements(self, ast_tree: ast.AST, ignored_lines: Set[int]) -> Set[Tuple[int, int]]:
        visitor = BranchVisitor(ignored_lines)
        visitor.visit(ast_tree)
        return visitor.arcs


class BranchVisitor(NextStatementVisitor):
    """
    Traverses the AST to identify logical control flow branches.
    """
    def __init__(self, ignored_lines: Set[int]):
        super().__init__(ignored_lines)
        self.arcs: Set[Tuple[int, int]] = set()

    def _add_arc(self, start: int, target_node: Optional[ast.AST]) -> None:
        if target_node and hasattr(target_node, 'lineno'):
            # Ignore same-line arcs (inline statements don't represent true line-level branches)
            if target_node.lineno != start:
                self.arcs.add((start, target_node.lineno))

    def _find_next_statement(self, node: ast.AST) -> Optional[ast.AST]:
        """
        Overrides base method to prevent control flow from escaping
        scope boundaries like functions or classes.
        """
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            return None
        return super()._find_next_statement(node)

    def visit_If(self, node: ast.If) -> None:
        if not self.is_ignored(node):
            start = node.lineno
            if node.body:
                self._add_arc(start, node.body[0])
            if node.orelse:
                self._add_arc(start, node.orelse[0])
            else:
                self._add_arc(start, self._find_next_statement(node))
        self.generic_visit(node)

    def _handle_loop(self, node: Any) -> None:
        if not self.is_ignored(node):
            start = node.lineno
            body_target, exit_target = self._get_loop_targets(node)
            self._add_arc(start, body_target)
            self._add_arc(start, exit_target)
        self.generic_visit(node)

    def visit_For(self, node: ast.For) -> None:
        self._handle_loop(node)

    def visit_AsyncFor(self, node: ast.AsyncFor) -> None:
        self._handle_loop(node)

    def visit_While(self, node: ast.While) -> None:
        self._handle_loop(node)

    def visit_Match(self, node: Any) -> None:
        if not self.is_ignored(node):
            start = getattr(node, 'lineno', -1)
            has_wildcard = False
            for case in getattr(node, 'cases', []):
                if getattr(case, 'body', None):
                    self._add_arc(start, case.body[0])

                pattern = getattr(case, 'pattern', None)
                if isinstance(pattern, getattr(ast, 'MatchAs', type(None))) and getattr(pattern, 'pattern', None) is None:
                    has_wildcard = True

            if not has_wildcard:
                self._add_arc(start, self._find_next_statement(node))
        self.generic_visit(node)
