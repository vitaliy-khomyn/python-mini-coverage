import ast
import dis


class CoverageMetric:
    def get_name(self):
        raise NotImplementedError

    def get_possible_elements(self, ast_tree, ignored_lines):
        raise NotImplementedError

    def calculate_stats(self, possible_elements, executed_data):
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


# ... existing StatementCoverage code ...
class StatementCoverage(CoverageMetric):
    def get_name(self):
        return "Statement"

    def get_possible_elements(self, ast_tree, ignored_lines):
        executable_lines = set()
        for node in ast.walk(ast_tree):
            if isinstance(node, ast.stmt):
                if node.lineno in ignored_lines:
                    continue
                if isinstance(node, ast.Expr) and isinstance(node.value, ast.Constant):
                    continue
                if isinstance(node, ast.Expr) and isinstance(node.value, (getattr(ast, 'Str', type(None)),
                                                                          getattr(ast, 'Num', type(None)))):
                    continue

                if hasattr(node, 'lineno'):
                    executable_lines.add(node.lineno)
        return executable_lines


class BranchCoverage(CoverageMetric):
    def get_name(self):
        return "Branch"

    def get_possible_elements(self, ast_tree, ignored_lines):
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
    Identifies atomic Boolean Conditions (MCDC foundation).
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
    Analyzes Python bytecode to determine control flow (jumps).
    This allows for more accurate branch coverage, handling implicit
    returns, short-circuiting, and generator states better than AST.
    """

    def get_name(self):
        return "Bytecode"

    def get_possible_elements(self, code_obj, ignored_lines=None):
        """
        Returns a set of (instruction_offset, target_offset) tuples representing jumps.
        Input is now a Code Object, not AST.
        """
        # Note: This requires the engine to pass the code object,
        # or we compile it here if needed.
        if not code_obj:
            return set()

        jumps = set()
        # dis.get_instructions yields Instruction objects
        # We need to handle nested code objects (functions/classes)
        self._analyze_code_object(code_obj, jumps)
        return jumps

    def _analyze_code_object(self, co, jumps):
        instructions = list(dis.get_instructions(co))

        for i, instr in enumerate(instructions):
            # Check for jump instructions
            # Opcodes like POP_JUMP_IF_FALSE (114), POP_JUMP_IF_TRUE (115),
            # JUMP_FORWARD (110), JUMP_ABSOLUTE (113), etc.
            if instr.opcode in dis.hasjabs or instr.opcode in dis.hasjrel:
                # Target is the jump destination
                target = instr.argval
                jumps.add((instr.offset, target))

                # Fallthrough: Most conditional jumps can also fall through to next instr
                # Unconditional jumps (JUMP_ABSOLUTE) do not fall through.
                if "JUMP_IF" in instr.opname or "FOR_ITER" in instr.opname:
                    if i + 1 < len(instructions):
                        next_instr = instructions[i + 1]
                        jumps.add((instr.offset, next_instr.offset))

        # Recurse into consts to find nested functions/classes
        for const in co.co_consts:
            if isinstance(const, type(co)):
                self._analyze_code_object(const, jumps)