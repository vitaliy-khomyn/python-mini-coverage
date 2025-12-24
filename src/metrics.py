import ast
import dis
import types
import sys
from typing import Set, Dict, Any, Optional, Union, Tuple, List


class CoverageMetric:
    """
    Abstract base class for coverage measurement strategies.
    """

    def get_name(self) -> str:
        """
        Return the display name of the metric.
        """
        raise NotImplementedError

    def get_possible_elements(self, source: Any, ignored_lines: Set[int]) -> Set[Any]:
        """
        Analyze the source (AST or Code Object) to determine all possible coverage targets.

        Args:
            source (Any): The parsed source tree (ast.Module) or compiled code object.
            ignored_lines (set): Set of line numbers marked with pragmas to ignore.

        Returns:
            set: A collection of elements (lines, arcs, or conditions) that should be covered.
        """
        raise NotImplementedError

    def calculate_stats(self, possible_elements: Set[Any], executed_data: Set[Any]) -> Dict[str, Any]:
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

            # Recursively scan exception handlers
            if hasattr(node, 'handlers') and isinstance(node.handlers, list):
                for handler in node.handlers:
                    if hasattr(handler, 'body'):
                        self._scan_body(handler.body, arcs, next_lineno, ignored_lines)


class ControlFlowGraph:
    """
    A representation of the Control Flow Graph (CFG) for a Python Code Object.

    Identifies Basic Blocks, computes edges (jumps/fallthroughs),
    exception handlers, and dominators.
    """

    def __init__(self, code: types.CodeType):
        self.code = code
        self.instructions = list(dis.get_instructions(code))
        self.offset_to_instr_idx = {instr.offset: i for i, instr in enumerate(self.instructions)}

        self.leaders = self._find_leaders()
        self.blocks = self._build_blocks()

        self.successors: Dict[int, Set[int]] = {b_start: set() for b_start, _ in self.blocks}
        self.predecessors: Dict[int, Set[int]] = {b_start: set() for b_start, _ in self.blocks}
        self._build_edges()

        self.dominators: Dict[int, Set[int]] = {}
        self._compute_dominators()

    def _find_leaders(self) -> Set[int]:
        """Find the starting offset of all basic blocks."""
        leaders = {0}

        for i, instr in enumerate(self.instructions):
            # Target of any jump is a leader
            if instr.opcode in dis.hasjabs or instr.opcode in dis.hasjrel:
                target = int(instr.argval)
                leaders.add(target)

                # Instruction following a jump is a leader
                if i + 1 < len(self.instructions):
                    leaders.add(self.instructions[i + 1].offset)

            # Instruction following a return/raise is a leader (unreachable or new block)
            if instr.opname in ('RETURN_VALUE', 'RAISE_VARARGS', 'RETURN_CONST'):
                if i + 1 < len(self.instructions):
                    leaders.add(self.instructions[i + 1].offset)

        # Exception Handlers are leaders (Python 3.11+)
        if sys.version_info >= (3, 11) and hasattr(self.code, 'co_exceptiontable'):
            try:
                # dis.parse_exception_table returns (start, end, target, depth, lasti)
                for _, _, target, _, _ in dis.parse_exception_table(self.code):  # type: ignore
                    leaders.add(target)
            except Exception:
                pass

        return leaders

    def _build_blocks(self) -> List[Tuple[int, int]]:
        """Construct (start, end) ranges for basic blocks."""
        sorted_leaders = sorted(list(self.leaders))
        blocks = []

        for i, start in enumerate(sorted_leaders):
            if i + 1 < len(sorted_leaders):
                end_leader = sorted_leaders[i + 1]
                end_leader_idx = self.offset_to_instr_idx[end_leader]
                end_instr = self.instructions[end_leader_idx - 1]
            else:
                end_instr = self.instructions[-1]

            blocks.append((start, end_instr.offset))
        return blocks

    def _build_edges(self) -> None:
        """Populate successors and predecessors based on jumps and fallthroughs."""
        for start, end in self.blocks:
            end_idx = self.offset_to_instr_idx[end]
            end_instr = self.instructions[end_idx]

            targets = []

            # 1. Jumps
            if end_instr.opcode in dis.hasjabs or end_instr.opcode in dis.hasjrel:
                targets.append(int(end_instr.argval))

            # 2. Fallthrough
            # Falls through if not an unconditional flow breaker
            is_unconditional = end_instr.opname in (
                'JUMP_ABSOLUTE', 'JUMP_FORWARD', 'RETURN_VALUE', 'RAISE_VARARGS', 'RETURN_CONST'
            )
            # Conditional jumps (POP_JUMP_IF_FALSE etc) also fall through
            if not is_unconditional:
                if end_idx + 1 < len(self.instructions):
                    targets.append(self.instructions[end_idx + 1].offset)

            # 3. Exception Edges (Simplified)
            # In a real CFG, exceptions can occur at almost any instruction.
            # Here we map them if we parsed leaders from the exception table.

            for t in targets:
                # Ensure target is a valid block start (it should be if leaders logic is correct)
                if t in self.successors:
                    self.successors[start].add(t)
                    self.predecessors[t].add(start)

    def _compute_dominators(self) -> None:
        """
        Compute dominators for each block using a standard iterative algorithm.
        Dom(n) = {n} U (Intersection of Dom(p) for all p in pred(n))
        """
        # Initialize
        all_nodes = set(self.successors.keys())
        self.dominators = {node: all_nodes.copy() for node in all_nodes}

        # Start node dominates itself
        start_node = 0
        if start_node in self.dominators:
            self.dominators[start_node] = {start_node}

        changed = True
        while changed:
            changed = False
            for node in all_nodes:
                if node == start_node:
                    continue

                preds = self.predecessors[node]
                if not preds:
                    continue

                # Intersection of all predecessors
                # Start with the first predecessor's dominators
                first_pred = next(iter(preds))
                new_dom = self.dominators[first_pred].copy()

                for p in preds:
                    new_dom &= self.dominators[p]

                new_dom.add(node)

                if new_dom != self.dominators[node]:
                    self.dominators[node] = new_dom
                    changed = True

    def get_jumps(self) -> Set[Tuple[int, int]]:
        """Return all edges as (source_instruction_offset, target_instruction_offset)"""
        jumps = set()
        for src, targets in self.successors.items():
            # src is the block start. We usually want the edge from the *end* instruction of the block
            # to the *start* instruction of the target block.
            # Find the end instruction of the 'src' block
            block_end = next(end for s, end in self.blocks if s == src)

            for t in targets:
                jumps.add((block_end, t))
        return jumps


class BytecodeControlFlow(CoverageMetric):
    """
    Analyzes Python bytecode to determine control flow jumps.
    Now uses a full Control Flow Graph (CFG) builder.
    """

    def get_name(self) -> str:
        return "Bytecode"

    def get_possible_elements(self, code_obj: Optional[types.CodeType], ignored_lines: Optional[Set[int]] = None) -> \
    Set[Tuple[int, int]]:
        if not code_obj:
            return set()

        jumps: Set[Tuple[int, int]] = set()
        self._analyze_code_object(code_obj, jumps)
        return jumps

    def _analyze_code_object(self, co: types.CodeType, jumps: Set[Tuple[int, int]]) -> None:
        # Build CFG for the current code object
        cfg = ControlFlowGraph(co)
        jumps.update(cfg.get_jumps())

        # Recurse into nested code objects (functions/classes)
        for const in co.co_consts:
            if isinstance(const, types.CodeType):
                self._analyze_code_object(const, jumps)


class ConditionCoverage(CoverageMetric):
    """
    True MC/DC Implementation.
    Identifies boolean jump instructions and verifies that both outcomes (True/False)
    were executed at the bytecode level.
    """

    def get_name(self) -> str:
        return "Condition"

    def get_possible_elements(self, code_obj: Optional[types.CodeType], ignored_lines: Optional[Set[int]] = None) -> \
    Set[Tuple[int, int]]:
        """
        Returns a set of expected arcs (from_offset, to_offset) specifically for BOOLEAN jumps.
        This includes POP_JUMP_IF_FALSE, POP_JUMP_IF_TRUE, etc.
        For each boolean jump, we expect TWO arcs: (offset, target) and (offset, next).
        """
        if not code_obj:
            return set()

        arcs: Set[Tuple[int, int]] = set()
        self._analyze_boolean_jumps(code_obj, arcs)
        return arcs

    def _analyze_boolean_jumps(self, co: types.CodeType, arcs: Set[Tuple[int, int]]) -> None:
        # We need instructions to find offsets
        instructions = list(dis.get_instructions(co))

        for i, instr in enumerate(instructions):
            # Instructions relevant for Boolean logic (short-circuiting)
            is_bool_jump = instr.opname in (
                'POP_JUMP_IF_FALSE', 'POP_JUMP_IF_TRUE',
                'JUMP_IF_FALSE_OR_POP', 'JUMP_IF_TRUE_OR_POP'
            )

            if is_bool_jump:
                # 1. Target Arc (Jump Taken)
                target = int(instr.argval)
                arcs.add((instr.offset, target))

                # 2. Fallthrough Arc (Jump Not Taken)
                # Ensure we don't go out of bounds
                if i + 1 < len(instructions):
                    next_offset = instructions[i + 1].offset
                    arcs.add((instr.offset, next_offset))

        # Recurse
        for const in co.co_consts:
            if isinstance(const, types.CodeType):
                self._analyze_boolean_jumps(const, arcs)