import ast
from typing import Set
from .base import CoverageMetric


class StatementCoverage(CoverageMetric):
    """
    Measures which executable lines of code were run.
    """

    def get_name(self) -> str:
        return "Statement"

    def get_possible_elements(self, ast_tree: ast.AST, ignored_lines: Set[int]) -> Set[int]:
        executable_lines: Set[int] = set()
        for node in ast.walk(ast_tree):
            if isinstance(node, ast.stmt):
                if node.lineno in ignored_lines:
                    continue

                # ignore constants (docstrings, standalone numbers)
                if isinstance(node, ast.Expr) and isinstance(node.value, ast.Constant):
                    continue

                # compatibility for < python 3.8
                if isinstance(node, ast.Expr) and isinstance(node.value, (getattr(ast, 'Str', type(None)),
                                                                          getattr(ast, 'Num', type(None)))):
                    continue

                if hasattr(node, 'lineno'):
                    executable_lines.add(node.lineno)
        return executable_lines
