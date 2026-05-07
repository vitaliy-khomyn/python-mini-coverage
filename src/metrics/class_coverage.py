import ast

from typing import Set, Tuple, Optional, Dict, Any

from .base import CoverageMetric
from .visitor import BaseVisitor

# (class_name, definition_line_no, init_first_executable_line_no)
ClassElement = Tuple[str, int, int]


class ClassCoverage(CoverageMetric):
    """
    Class Coverage Implementation.
    Identifies classes and checks if they have been instantiated.
    """

    def get_name(self) -> str:
        return "Class"

    def get_possible_elements(
        self,
        tree: ast.AST,
        ignored_lines: Optional[Set[int]] = None
    ) -> Set[ClassElement]:
        """
        Returns a set of tuples, where each tuple represents a class
        that can be covered (i.e., has an __init__ method).
        """
        visitor = ClassVisitor(ignored_lines or set())
        visitor.visit(tree)
        return visitor.classes

    def calculate_stats(
        self,
        possible_elements: Set[ClassElement],
        executed_elements: Set[int]
    ) -> Dict[str, Any]:
        """
        Calculates coverage stats for classes.
        'executed_elements' for this metric is the set of executed line numbers.
        A class is covered if the first line of its __init__ is executed.
        """
        return super().calculate_stats(possible_elements, executed_elements, key=lambda c: c[2])


class ClassVisitor(BaseVisitor):
    def __init__(self, ignored_lines: Set[int]):
        super().__init__(ignored_lines)
        self.classes: Set[ClassElement] = set()

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        if self.is_ignored(node):
            self.generic_visit(node)
            return

        init_method = next((item for item in node.body if isinstance(item, ast.FunctionDef) and item.name == '__init__'), None)

        if init_method:
            first_exec_line = next((stmt.lineno for stmt in init_method.body if not self._is_docstring(stmt)), None)
            if first_exec_line:
                self.classes.add((node.name, node.lineno, first_exec_line))

        self.generic_visit(node)
