import ast
from typing import Set, Tuple, Optional
from .base import CoverageMetric


class BranchCoverage(CoverageMetric):
    """
    Measures control flow branches (arcs) between lines.
    """

    def get_name(self) -> str:
        return "Branch"

    def get_possible_elements(self, ast_tree: ast.AST, ignored_lines: Set[int]) -> Set[Tuple[int, int]]:
        arcs: Set[Tuple[int, int]] = set()
        if hasattr(ast_tree, 'body'):
            # ast_tree is expected to be a Module or similar container
            self._scan_body(getattr(ast_tree, 'body'), arcs, None, ignored_lines)
        return arcs

    def _scan_body(self, statements: list, arcs: Set[Tuple[int, int]], next_lineno: Optional[int],
                   ignored_lines: Set[int]) -> None:
        """
        Recursively scan a block of statements to identify jump targets.
        """
        for i, node in enumerate(statements):
            current_next = next_lineno
            if i + 1 < len(statements):
                current_next = statements[i + 1].lineno

            if hasattr(node, 'lineno') and node.lineno in ignored_lines:
                continue

            self._analyze_node(node, arcs, current_next, ignored_lines)

    def _analyze_node(self, node: ast.AST, arcs: Set[Tuple[int, int]], next_lineno: Optional[int],
                      ignored_lines: Set[int]) -> None:
        """
        Analyze a single AST node to find control flow structures.
        """
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef, ast.Module)):
            self._scan_body(node.body, arcs, None, ignored_lines)
            return

        if isinstance(node, ast.If):
            start = node.lineno
            if node.body:
                arcs.add((start, node.body[0].lineno))
                self._scan_body(node.body, arcs, next_lineno, ignored_lines)
            if node.orelse:
                arcs.add((start, node.orelse[0].lineno))
                self._scan_body(node.orelse, arcs, next_lineno, ignored_lines)
            else:
                if next_lineno:
                    arcs.add((start, next_lineno))

        elif isinstance(node, (ast.For, ast.AsyncFor, ast.While)):
            start = node.lineno
            if node.body:
                arcs.add((start, node.body[0].lineno))
                self._scan_body(node.body, arcs, start, ignored_lines)
            if node.orelse:
                arcs.add((start, node.orelse[0].lineno))
                self._scan_body(node.orelse, arcs, next_lineno, ignored_lines)
            elif next_lineno:
                arcs.add((start, next_lineno))

        elif hasattr(ast, 'Match') and isinstance(node, ast.Match):
            start = node.lineno
            has_wildcard = False
            for case in node.cases:
                if case.body:
                    arcs.add((start, case.body[0].lineno))
                    self._scan_body(case.body, arcs, next_lineno, ignored_lines)
                if isinstance(case.pattern, getattr(ast, 'MatchAs', type(None))) and case.pattern.pattern is None:
                    has_wildcard = True
            if not has_wildcard and next_lineno:
                arcs.add((start, next_lineno))

        else:
            if hasattr(node, 'body') and isinstance(node.body, list):
                self._scan_body(node.body, arcs, next_lineno, ignored_lines)
            if hasattr(node, 'orelse') and isinstance(node.orelse, list):
                self._scan_body(node.orelse, arcs, next_lineno, ignored_lines)
            if hasattr(node, 'finalbody') and isinstance(node.finalbody, list):
                self._scan_body(node.finalbody, arcs, next_lineno, ignored_lines)

            if hasattr(node, 'handlers') and isinstance(node.handlers, list):
                for handler in node.handlers:
                    if hasattr(handler, 'body'):
                        self._scan_body(handler.body, arcs, next_lineno, ignored_lines)
