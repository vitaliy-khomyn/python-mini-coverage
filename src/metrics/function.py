import ast
from typing import Set, Tuple, Optional, Dict, Any

from .base import CoverageMetric

# Using a tuple to store info about each function
# (function_name, definition_line_no, first_executable_line_no)
FunctionElement = Tuple[str, int, int]


class FunctionCoverage(CoverageMetric):
    """
    Function Coverage Implementation.
    Identifies functions/methods and checks if their body has been executed.
    """

    def get_name(self) -> str:
        return "Function"

    def get_possible_elements(
        self,
        tree: ast.AST,
        ignored_lines: Optional[Set[int]] = None
    ) -> Set[FunctionElement]:
        """
        Returns a set of tuples, where each tuple represents a function
        that can be covered.
        """
        visitor = FunctionVisitor(ignored_lines or set())
        visitor.visit(tree)
        return visitor.functions

    def calculate_stats(
        self,
        possible_elements: Set[FunctionElement],
        executed_elements: Set[int]
    ) -> Dict[str, Any]:
        """
        Calculates coverage stats for functions.
        'executed_elements' for this metric is the set of executed line numbers.
        """
        if not possible_elements:
            return {
                'pct': 100.0, 'missing': set(), 'executed': set(),
                'possible': set(), 'ratio': "0/0"
            }

        covered_elements = {
            func for func in possible_elements if func[2] in executed_elements
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

    def map_missing_elements(
        self,
        missing_elements: Set[FunctionElement]
    ) -> Dict[int, str]:
        """
        Maps missing functions to a human-readable format for reporting.
        Returns a dict of {line_number: "description"}.
        """
        return {
            func[1]: f"Function '{func[0]}' was not called"
            for func in missing_elements
        }


class FunctionVisitor(ast.NodeVisitor):
    def __init__(self, ignored_lines: Set[int]):
        self.ignored_lines = ignored_lines
        self.functions: Set[FunctionElement] = set()

    def _is_docstring(self, stmt: ast.stmt) -> bool:
        """
        Checks if an AST statement is a docstring.
        This is compatible with Python versions before and after 3.8.
        """
        if not isinstance(stmt, ast.Expr):
            return False

        # Python 3.8+ uses ast.Constant for strings
        if isinstance(stmt.value, ast.Constant):
            return isinstance(stmt.value.value, str)

        # Python < 3.8 used ast.Str
        return hasattr(ast, 'Str') and isinstance(stmt.value, ast.Str)

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        self._analyze_function(node)
        self.generic_visit(node)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        self._analyze_function(node)
        self.generic_visit(node)

    def _analyze_function(self, node: ast.AST) -> None:
        if node.lineno in self.ignored_lines:
            return

        first_exec_line = next((stmt.lineno for stmt in node.body if not self._is_docstring(stmt)), None)

        if first_exec_line:
            self.functions.add((node.name, node.lineno, first_exec_line))
