import ast
import dis


class CoverageMetric:
    """
    Abstract base class for coverage measurement strategies.
    """

    def get_name(self):
        """
        Return the display name of the metric.
        """
        raise NotImplementedError

    def get_possible_elements(self, ast_tree, ignored_lines):
        """
        Analyze the AST (or Code Object) to determine all possible coverage targets.

        Args:
            ast_tree (ast.Module): The parsed source tree.
            ignored_lines (set): Set of line numbers marked with pragmas to ignore.

        Returns:
            set: A collection of elements (lines, arcs, or conditions) that should be covered.
        """
        raise NotImplementedError

    def calculate_stats(self, possible_elements, executed_data):
        """
        Compare possible elements against executed data to calculate coverage.

        Args:
            possible_elements (set): The set of static elements found by analysis.
            executed_data (set): The set of dynamic elements collected during execution.

        Returns:
            dict: Statistics including 'pct' (float), 'missing' (set), 'executed' (set).
        """
        if not possible_elements:
            return {
                'pct': 100.0,
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
    """
    Measures which executable lines of code were run.
    """

    def get_name(self):
        return "Statement"

    def get_possible_elements(self, ast_tree, ignored_lines):
        executable_lines = set()
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


class BranchCoverage(CoverageMetric):
    """
    Measures control flow branches (arcs) between lines.
    """

    def get_name(self):
        return "Branch"

    def get_possible_elements(self, ast_tree, ignored_lines):
        arcs = set()
        if hasattr(ast_tree, 'body'):
            self._scan_body(ast_tree.body, arcs, None, ignored_lines)
        return arcs

    def _scan_body(self, statements, arcs, next_lineno, ignored_lines):
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

    def _analyze_node(self, node, arcs, next_lineno, ignored_lines):
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


class ConditionCoverage(CoverageMetric):
    """
    Identifies atomic Boolean Conditions for MCDC analysis.
    """

    def get_name(self):
        return "Condition"

    def get_possible_elements(self, ast_tree, ignored_lines):
        """
        Returns a set of tuples representing individual boolean conditions.
        We include node type to differentiate a parent BoolOp from its first child
        if they share the same location.
        Structure: (lineno, col_offset, node_type_name)
        """
        conditions = set()
        for node in ast.walk(ast_tree):
            if hasattr(node, 'lineno') and node.lineno in ignored_lines:
                continue

            if isinstance(node, ast.BoolOp):
                for value in node.values:
                    if hasattr(value, 'lineno') and hasattr(value, 'col_offset'):
                        conditions.add((value.lineno, value.col_offset, type(value).__name__))
        return conditions


class BytecodeControlFlow(CoverageMetric):
    """
    Analyzes Python bytecode to determine control flow jumps.
    """

    def get_name(self):
        return "Bytecode"

    def get_possible_elements(self, code_obj, ignored_lines=None):
        if not code_obj:
            return set()

        jumps = set()
        self._analyze_code_object(code_obj, jumps)
        return jumps

    def _analyze_code_object(self, co, jumps):
        instructions = list(dis.get_instructions(co))

        for i, instr in enumerate(instructions):
            if instr.opcode in dis.hasjabs or instr.opcode in dis.hasjrel:
                target = instr.argval
                jumps.add((instr.offset, target))

                # fallthrough logic for conditional jumps
                if "JUMP_IF" in instr.opname or "FOR_ITER" in instr.opname:
                    if i + 1 < len(instructions):
                        next_instr = instructions[i + 1]
                        jumps.add((instr.offset, next_instr.offset))

        for const in co.co_consts:
            if isinstance(const, type(co)):
                self._analyze_code_object(const, jumps)