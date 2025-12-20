import ast


class CoverageMetric:
    def get_name(self):
        raise NotImplementedError

    def get_possible_elements(self, ast_tree, ignored_lines):
        raise NotImplementedError

    def calculate_stats(self, possible_elements, executed_data):
        if not possible_elements:
            return {
                'pct': 100.0,  # Empty file is technically "fully covered" or 0, convention 100
                'missing': set(),
                'executed': set(),
                'possible': set()
            }

        hit = possible_elements.intersection(executed_data)
        missing = possible_elements - hit
        pct = (len(hit) / len(possible_elements)) * 100

        return {
            'pct': pct,
            'missing': missing,
            'executed': hit,
            'possible': possible_elements
        }


class StatementCoverage(CoverageMetric):
    def get_name(self):
        return "Statement"

    def get_possible_elements(self, ast_tree, ignored_lines):
        executable_lines = set()
        for node in ast.walk(ast_tree):
            if isinstance(node, ast.stmt):
                # Check for Pragma exclusion
                if node.lineno in ignored_lines:
                    continue

                # Use ast.Constant for Python 3.8+ (replaces ast.Str/ast.Num)
                if isinstance(node, ast.Expr) and isinstance(node.value, ast.Constant):
                    # Check if it's a docstring (string constant)
                    if isinstance(node.value.value, str):
                        continue
                if hasattr(node, 'lineno'):
                    executable_lines.add(node.lineno)
        return executable_lines


class BranchCoverage(CoverageMetric):
    def get_name(self):
        return "Branch"

    def get_possible_elements(self, ast_tree, ignored_lines):
        """
        Returns a set of arcs (start_line, end_line) representing possible jumps.
        Excludes arcs starting on ignored lines.
        """
        arcs = set()
        if hasattr(ast_tree, 'body'):
            self._scan_body(ast_tree.body, arcs, None, ignored_lines)
        return arcs

    def _scan_body(self, statements, arcs, next_lineno, ignored_lines):
        for i, node in enumerate(statements):
            current_next = next_lineno
            if i + 1 < len(statements):
                current_next = statements[i + 1].lineno

            if hasattr(node, 'lineno') and node.lineno in ignored_lines:
                continue

            self._analyze_node(node, arcs, current_next, ignored_lines)

    def _analyze_node(self, node, arcs, next_lineno, ignored_lines):
        # Recursively scan children
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef, ast.Module)):
            self._scan_body(node.body, arcs, None, ignored_lines)
            return

        # 1. IF Statements
        if isinstance(node, ast.If):
            start = node.lineno

            # True Path
            if node.body:
                arcs.add((start, node.body[0].lineno))
                self._scan_body(node.body, arcs, next_lineno, ignored_lines)

            # False Path
            if node.orelse:
                arcs.add((start, node.orelse[0].lineno))
                self._scan_body(node.orelse, arcs, next_lineno, ignored_lines)
            else:
                if next_lineno:
                    arcs.add((start, next_lineno))

        # 2. Loops
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

        # 3. Match Statements
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

        # 4. Standard structural recursion
        else:
            if hasattr(node, 'body') and isinstance(node.body, list):
                self._scan_body(node.body, arcs, next_lineno, ignored_lines)
            if hasattr(node, 'orelse') and isinstance(node.orelse, list):
                self._scan_body(node.orelse, arcs, next_lineno, ignored_lines)
            if hasattr(node, 'finalbody') and isinstance(node.finalbody, list):
                self._scan_body(node.finalbody, arcs, next_lineno, ignored_lines)


class ConditionCoverage(CoverageMetric):
    """
    Identifies atomic Boolean Conditions (MCDC foundation).

    LIMITATION: Without bytecode analysis, we cannot determine dynamically
    which individual conditions were evaluated in a short-circuit expression.

    This implementation currently performs Static Analysis to identify
    complex boolean logic (AND/OR) to highlight testing complexity.
    """

    def get_name(self):
        return "Condition"

    def get_possible_elements(self, ast_tree, ignored_lines):
        """
        Returns a set of (lineno, col_offset) tuples representing
        individual boolean conditions found in BoolOp nodes.
        """
        conditions = set()
        for node in ast.walk(ast_tree):
            if hasattr(node, 'lineno') and node.lineno in ignored_lines:
                continue

            if isinstance(node, ast.BoolOp):
                # A BoolOp (e.g., 'a and b') has a list of values.
                # Each value is a condition.
                for value in node.values:
                    # We use col_offset to uniquely identify the condition on the line
                    if hasattr(value, 'lineno') and hasattr(value, 'col_offset'):
                        conditions.add((value.lineno, value.col_offset))
        return conditions