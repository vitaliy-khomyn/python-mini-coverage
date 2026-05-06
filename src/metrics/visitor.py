import ast

from typing import Optional, List, Set


class BaseVisitor(ast.NodeVisitor):
    """Base for AST visitors, providing common helpers."""

    def __init__(self, ignored_lines: Optional[Set[int]] = None) -> None:
        self.ignored_lines = ignored_lines or set()

    def is_ignored(self, node: ast.AST) -> bool:
        """Checks if a node's line number is in the ignored set."""
        return getattr(node, 'lineno', -1) in self.ignored_lines

    def _is_docstring(self, stmt: ast.stmt) -> bool:
        """
        Checks if an AST statement is a docstring.
        This is compatible with Python versions before and after 3.8.
        """
        if not isinstance(stmt, ast.Expr):
            return False

        # python 3.8+ uses ast.Constant for strings
        if isinstance(stmt.value, ast.Constant):
            return isinstance(stmt.value.value, str)

        # Python < 3.8 used ast.Str
        return hasattr(ast, 'Str') and isinstance(stmt.value, ast.Str)


class NextStatementVisitor(BaseVisitor):
    """
    An AST visitor that keeps track of parent nodes to allow finding
    the next logical statement that follows a given block.
    This is useful for finding the exit target of loops or if-statements.
    """
    def __init__(self, ignored_lines: Optional[Set[int]] = None) -> None:
        super().__init__(ignored_lines)
        self.path: List[ast.AST] = []

    def visit(self, node: ast.AST) -> None:
        self.path.append(node)
        super().visit(node)
        self.path.pop()

    def _find_next_statement(self, node: ast.AST) -> Optional[ast.AST]:
        """
        Finds the statement that executes immediately after the given node.
        """
        if len(self.path) < 2:
            return None

        parent = self.path[-2]

        for _, field_value in ast.iter_fields(parent):
            if isinstance(field_value, list):
                try:
                    idx = field_value.index(node)
                    if idx + 1 < len(field_value):
                        return field_value[idx + 1]
                except ValueError:
                    continue

        current_node = self.path.pop()
        next_stmt = self._find_next_statement(parent)
        self.path.append(current_node)  # Restore path
        return next_stmt
