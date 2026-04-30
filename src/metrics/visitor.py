import ast
from typing import Optional, List


class NextStatementVisitor(ast.NodeVisitor):
    """
    An AST visitor that keeps track of parent nodes to allow finding
    the next logical statement that follows a given block.
    This is useful for finding the exit target of loops or if-statements.
    """
    def __init__(self) -> None:
        # Stack of nodes in the current traversal path
        self.path: List[ast.AST] = []

    def visit(self, node: ast.AST) -> None:
        # Before visiting children, add node to path
        self.path.append(node)
        # Default visitor will call visit_FIELD on children
        super().visit(node)
        # After visiting children, remove node from path
        self.path.pop()

    def _find_next_statement(self, node: ast.AST) -> Optional[ast.AST]:
        """
        Finds the statement that executes immediately after the given node.
        """
        # We need at least a node and its parent
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
