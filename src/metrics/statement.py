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
            is_match_case = type(node).__name__ == 'match_case'

            if isinstance(node, ast.stmt) or is_match_case:
                # match_case nodes don't have a lineno, but their patterns do
                node_lineno = getattr(node, 'lineno', getattr(getattr(node, 'pattern', None), 'lineno', -1))

                if node_lineno in ignored_lines:
                    continue

                # Compiler directives do not generate executable bytecode line events
                if isinstance(node, (ast.Global, ast.Nonlocal)):
                    continue

                # ignore constants (docstrings, standalone numbers)
                if isinstance(node, ast.Expr) and isinstance(node.value, ast.Constant):
                    continue

                # compatibility for < python 3.8
                if isinstance(node, ast.Expr) and isinstance(node.value, (getattr(ast, 'Str', type(None)),
                                                                          getattr(ast, 'Num', type(None)))):
                    continue

                if node_lineno != -1:
                    executable_lines.add(node_lineno)
        return executable_lines
