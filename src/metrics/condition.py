import ast
import collections
import dis
import sys
import types

from typing import Set, Tuple, Optional, Dict, Any, List

from .base import CoverageMetric, StaticSourceType
from .boolean_vector import BooleanVectorEvaluator
from ..engine.trace_data import TraceDataType


class OutcomeFormatter:
    """
    Handles string formatting, redundancy filtering, and statistics
    aggregation for condition-based coverage metrics.
    """
    @staticmethod
    def format_line_outcomes(global_line_stats: Dict[int, Any], filter_redundant: bool = False) -> Dict[int, Any]:
        result = {}
        for lineno, stats in global_line_stats.items():
            decisions_out = []

            for decision in stats.get('decisions', []):
                cond_count = decision.get('conditions', 0)
                if cond_count == 0:
                    continue

                missing = decision.get('missing', [])
                if filter_redundant:
                    missing = OutcomeFormatter._filter_redundant_vectors(missing)

                def sort_vector(item: Dict[str, Any]) -> Tuple[int, ...]:
                    if 'vector' not in item:
                        return (999,)
                    order = {"True": 0, "False": 1, "-": 2, "?": 3}
                    return tuple(order.get(str(v), 4) for v in item['vector'])

                missing = sorted(missing, key=sort_vector)
                executed = sorted(decision.get('executed', []), key=sort_vector)

                d_names = decision.get('condition_names', [])
                d_names = d_names[:cond_count]

                tot = decision.get('total_possible', len(decision.get('ops', [])) + 1)
                covered = tot - len(missing)
                ratio = f"{covered}/{tot}"

                decisions_out.append({
                    'missing': missing,
                    'executed': executed,
                    'conditions': cond_count,
                    'condition_names': d_names,
                    'ratio': ratio,
                    'covered': covered,
                    'total': tot
                })

            if decisions_out:
                # Backwards compatibility: return dict if only 1 decision, else list of dicts
                if len(decisions_out) == 1:
                    result[lineno] = decisions_out[0]
                else:
                    result[lineno] = decisions_out

        return result

    @staticmethod
    def _filter_redundant_vectors(raw_items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Filter out intermediate missing vectors that are covered by more specific ones."""
        if not raw_items:
            return []

        indices_to_remove = set()
        for i, item_a in enumerate(raw_items):
            if item_a['terminal']:
                continue
            vec_a = item_a['vector']
            try:
                stop_idx = vec_a.index("?")
                prefix_a = vec_a[:stop_idx]
            except ValueError:
                prefix_a = vec_a

            for j, item_b in enumerate(raw_items):
                if i == j:
                    continue
                vec_b = item_b['vector']
                if len(vec_b) >= len(prefix_a) and vec_b[:len(prefix_a)] == prefix_a:
                    indices_to_remove.add(i)
                    break

        return [
            {'vector': [v if v != "?" else "-" for v in item['vector']], 'result': item['result'], 'terminal': item['terminal']}
            for i, item in enumerate(raw_items) if i not in indices_to_remove
        ]

    @staticmethod
    def format_global_stats(stats: Dict[str, Any], missing_outcomes: Dict[int, Any]) -> None:
        """
        Mutates the top-level stats dictionary to reflect condition vectors
        instead of raw bytecode arcs.
        """
        stats['missing_outcomes'] = missing_outcomes

        total_conditions = 0
        missing_conditions = []
        for lineno, decisions in missing_outcomes.items():
            if isinstance(decisions, dict):
                decisions = [decisions]

            for outcome in decisions:
                total_conditions += outcome.get('total', 0)
                for m in outcome.get('missing', []):
                    msg = m.get('message')
                    if not msg:
                        vec_str = ", ".join(m.get('vector', []))
                        res = m.get('result', '?')
                        msg = f"Vector ({vec_str}) -> {res}"
                    missing_conditions.append(f"Line {lineno}: {msg}")

        stats['total'] = total_conditions
        stats['missing'] = missing_conditions
        stats['covered'] = total_conditions - len(missing_conditions)
        stats['pct'] = round((stats['covered'] / total_conditions) * 100, 2) if total_conditions > 0 else 100.0
        stats['ratio'] = f"{stats['covered']}/{total_conditions}"


class ConditionNameExtractor(ast.NodeVisitor):
    """Extracts readable string representations of boolean conditions from the AST."""
    def __init__(self) -> None:
        self.names: Dict[Tuple[int, int], List[str]] = collections.defaultdict(list)
        self.extracted_nodes: Set[int] = set()
        self.code_id_stack: List[int] = [1]

    def _enter_scope(self, node: ast.AST) -> None:
        self.code_id_stack.append(getattr(node, 'lineno', self.code_id_stack[-1]))

    def _exit_scope(self) -> None:
        if len(self.code_id_stack) > 1:
            self.code_id_stack.pop()

    def _safe_unparse(self, node: ast.AST) -> str:
        try:
            text = ast.unparse(node)
            text = " ".join(text.split())  # collapse newlines and spaces
            if len(text) > 30:
                return text[:27] + "..."
            return text
        except Exception:
            return "Cond"

    def _add_leaves(self, node: ast.AST, lineno: int) -> None:
        if id(node) in self.extracted_nodes:
            return
        self.extracted_nodes.add(id(node))

        if isinstance(node, ast.BoolOp):
            for val in node.values:
                self._add_leaves(val, lineno)
        elif isinstance(node, ast.Compare) and len(node.ops) > 1:
            # Break down chained comparisons (e.g. 1 < x < 10) into individual bounds
            left = node.left
            for op, right in zip(node.ops, node.comparators):
                sub_comp = ast.Compare(left=left, ops=[op], comparators=[right])
                self.names[(lineno, self.code_id_stack[-1])].append(self._safe_unparse(sub_comp))
                left = right
        else:
            self.names[(lineno, self.code_id_stack[-1])].append(self._safe_unparse(node))

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        self._enter_scope(node)
        self.generic_visit(node)
        self._exit_scope()

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        self._enter_scope(node)
        self.generic_visit(node)
        self._exit_scope()

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        self._enter_scope(node)
        self.generic_visit(node)
        self._exit_scope()

    def visit_Lambda(self, node: ast.Lambda) -> None:
        self._enter_scope(node)
        self.generic_visit(node)
        self._exit_scope()

    def visit_If(self, node: ast.If) -> None:
        self._add_leaves(node.test, getattr(node, 'lineno', -1))
        self.generic_visit(node)

    def visit_While(self, node: ast.While) -> None:
        self._add_leaves(node.test, getattr(node, 'lineno', -1))
        self.generic_visit(node)

    def visit_Assert(self, node: ast.Assert) -> None:
        self._add_leaves(node.test, getattr(node, 'lineno', -1))
        self.generic_visit(node)

    def visit_IfExp(self, node: ast.IfExp) -> None:
        self._add_leaves(node.test, getattr(node, 'lineno', -1))
        self.generic_visit(node)

    def visit_BoolOp(self, node: ast.BoolOp) -> None:
        if id(node) not in self.extracted_nodes:
            self._add_leaves(node, getattr(node, 'lineno', -1))
        self.generic_visit(node)

    def visit_Compare(self, node: ast.Compare) -> None:
        if len(node.ops) > 1 and id(node) not in self.extracted_nodes:
            self._add_leaves(node, getattr(node, 'lineno', -1))
        self.generic_visit(node)

    def visit_Match(self, node: Any) -> None:
        for case in getattr(node, 'cases', []):
            guard = getattr(case, 'guard', None)
            if guard:
                self._add_leaves(guard, getattr(guard, 'lineno', getattr(node, 'lineno', -1)))
        self.generic_visit(node)

    def _visit_comprehension(self, node: ast.AST) -> None:
        self._enter_scope(node)
        for gen in getattr(node, 'generators', []):
            if hasattr(gen, 'ifs'):
                for if_node in gen.ifs:
                    self._add_leaves(if_node, getattr(node, 'lineno', -1))
        self.generic_visit(node)
        self._exit_scope()

    def visit_GeneratorExp(self, node: ast.GeneratorExp) -> None:
        self._visit_comprehension(node)
    def visit_ListComp(self, node: ast.ListComp) -> None:
        self._visit_comprehension(node)
    def visit_SetComp(self, node: ast.SetComp) -> None:
        self._visit_comprehension(node)
    def visit_DictComp(self, node: ast.DictComp) -> None:
        self._visit_comprehension(node)


class ConditionCoverage(CoverageMetric):
    """
    Condition Coverage Implementation.
    Identifies boolean jump instructions and verifies that both outcomes (True/False)
    were executed at the bytecode level.
    """

    # Opcodes that represent boolean decisions in Python bytecode
    BOOL_OPS = {
        'POP_JUMP_IF_FALSE',
        'POP_JUMP_IF_TRUE',
        'JUMP_IF_FALSE_OR_POP',
        'JUMP_IF_TRUE_OR_POP',
        'POP_JUMP_FORWARD_IF_FALSE',
        'POP_JUMP_FORWARD_IF_TRUE',
        'POP_JUMP_BACKWARD_IF_FALSE',
        'POP_JUMP_BACKWARD_IF_TRUE'
    }

    # Opcodes to skip when calculating fallthrough offsets (pseudo-instructions)
    IGNORED_OPS = {
        'EXTENDED_ARG',
        'CACHE',
        'KW_NAMES',
        'RESUME',
        'NOP',
        'PRECALL',         # Python 3.11
        'COPY_FREE_VARS',  # Python 3.11
        'NOT_TAKEN'        # Pseudo-instruction in some 3.12+ dis outputs
    }

    def __init__(self) -> None:
        super().__init__()
        self.valid_condition_lines: Optional[Set[int]] = None
        self.condition_names: Dict[Tuple[int, int], List[str]] = {}

    def get_name(self) -> str:
        return "Condition"

    def get_required_static_source(self) -> StaticSourceType:
        return StaticSourceType.CODE_OBJECT

    def get_required_dynamic_data(self) -> TraceDataType:
        return TraceDataType.INSTRUCTION_ARCS

    def set_ast(self, tree: ast.AST) -> None:
        self.valid_condition_lines = set()

        extractor = ConditionNameExtractor()
        extractor.code_id_stack = [getattr(tree, 'lineno', 1)]
        extractor.visit(tree)
        self.condition_names = extractor.names

        for node in ast.walk(tree):
            if isinstance(node, (ast.If, ast.While, ast.Assert, ast.IfExp, ast.BoolOp, ast.Compare)):
                self._add_lines(node)
            elif hasattr(ast, 'Match') and isinstance(node, getattr(ast, 'Match', type(None))):
                self._add_lines(node)
            elif isinstance(node, (ast.ListComp, ast.SetComp, ast.DictComp, ast.GeneratorExp)):
                self._add_lines(node)

    def _add_lines(self, node: ast.AST) -> None:
        start = getattr(node, 'lineno', -1)
        end = getattr(node, 'end_lineno', start)
        if end is None:
            end = start
        if start > 0:
            self.valid_condition_lines.update(range(start, end + 1))

    def get_possible_elements(
        self,
        code_obj: Optional[types.CodeType],
        ignored_lines: Optional[Set[int]] = None
    ) -> Set[Tuple[int, int, int]]:
        """
        Returns a set of expected arcs (code_id, from_offset, to_offset) specifically for BOOLEAN jumps.
        This includes POP_JUMP_IF_FALSE, POP_JUMP_IF_TRUE, etc.
        For each boolean jump, we expect TWO arcs: (offset, target) and (offset, next).
        """
        if not code_obj:
            return set()

        arcs: Set[Tuple[int, int, int]] = set()
        self._analyze_boolean_jumps(code_obj, arcs)
        return arcs

    def _get_instructions(self, co: types.CodeType) -> List[Any]:
        # Use show_caches=True to ensure we see all instruction slots (Python 3.11+)
        if sys.version_info >= (3, 11):
            return list(dis.get_instructions(co, show_caches=True))
        return list(dis.get_instructions(co))

    def _find_next_instr(self, instructions: List[Any], current_idx: int) -> Optional[int]:
        """Find the offset of the next 'real' instruction, skipping pseudo-ops."""
        next_idx = current_idx + 1
        while next_idx < len(instructions):
            if instructions[next_idx].opname in self.IGNORED_OPS:
                next_idx += 1
                continue
            return instructions[next_idx].offset
        return None

    def _analyze_boolean_jumps(self, co: types.CodeType, arcs: Set[Tuple[int, int, int]]) -> None:
        # instructions to find offsets
        instructions = self._get_instructions(co)
        code_id = co.co_firstlineno

        current_line = code_id
        for i, instr in enumerate(instructions):
            if getattr(instr, 'starts_line', None) is not None:
                current_line = instr.starts_line

            # instructions relevant for boolean logic
            # includes python 3.11+ directional variants
            is_bool_jump = instr.opname in self.BOOL_OPS

            if is_bool_jump:
                # Ignore artificial compiler instructions that lack a line number
                if hasattr(instr, 'positions'):
                    lineno = instr.positions.lineno if instr.positions else None
                else:
                    lineno = current_line

                if not lineno:
                    continue

                if self.valid_condition_lines is not None and lineno not in self.valid_condition_lines:
                    continue

                # 1. target arc (Jump Taken)
                target = int(instr.argval)
                arcs.add((code_id, instr.offset, target))

                # 2. fallthrough arc (Jump Not Taken)
                next_offset = self._find_next_instr(instructions, i)
                if next_offset is not None:
                    arcs.add((code_id, instr.offset, next_offset))

        # recurse
        for const in co.co_consts:
            if isinstance(const, types.CodeType):
                self._analyze_boolean_jumps(const, arcs)

    def map_missing_arcs(self, code_obj: types.CodeType, missing_arcs: Set[Tuple[int, int, int]], executed_arcs: Set[Tuple[int, int, int]]) -> Dict[int, Any]:
        """
        Map missing bytecode arcs to source line numbers with human-readable labels.
        Returns: {lineno: {'missing': [{'vector': '...', 'terminal': bool}], 'ratio': '3/4'}}
        """
        # Accumulate stats per line across all code objects (handling lambdas etc)
        # Structure: lineno -> {'total': int, 'missing': [], 'executed': [], 'conditions': int}
        global_line_stats = collections.defaultdict(lambda: {'total': 0, 'missing': [], 'executed': [], 'conditions': 0})

        if not code_obj:
            return {}

        self._collect_line_ops(code_obj, global_line_stats)
        self._analyze_line_ops(global_line_stats, missing_arcs, executed_arcs)

        return OutcomeFormatter.format_line_outcomes(global_line_stats, filter_redundant=True)

    def _collect_line_ops(self, co: types.CodeType, line_stats: Dict[int, Any]) -> None:
        """Recursively visit code objects and group boolean instructions by line number."""
        try:
            instructions = self._get_instructions(co)
        except Exception:
            instructions = []

        if instructions:
            current_line = co.co_firstlineno
            line_ops = collections.defaultdict(list)
            for i, instr in enumerate(instructions):
                if getattr(instr, 'starts_line', None) is not None:
                    current_line = instr.starts_line

                if instr.opname in self.BOOL_OPS:
                    if hasattr(instr, 'positions'):
                        lineno = instr.positions.lineno if instr.positions else None
                    else:
                        lineno = current_line

                    if lineno and lineno > 0:
                        if self.valid_condition_lines is not None and lineno not in self.valid_condition_lines:
                            continue

                        line_ops[lineno].append({
                            'instr': instr,
                            'next_offset': self._find_next_instr(instructions, i),
                            'code_id': co.co_firstlineno
                        })

            for lineno, ops in line_ops.items():
                ops.sort(key=lambda x: x['instr'].offset)

                names = self.condition_names.get((lineno, co.co_firstlineno))
                if names is None:
                    for (l, cid), n in self.condition_names.items():
                        if l == lineno:
                            names = n
                            break

                decision = {
                    'ops': ops,
                    'code_id': co.co_firstlineno,
                    'condition_names': names or []
                }
                line_stats[lineno].setdefault('decisions', []).append(decision)

        # Evaluate inner constants after outer block (Pre-Order) to match AST extraction order
        for const in co.co_consts:
            if isinstance(const, types.CodeType):
                self._collect_line_ops(const, line_stats)

    def _analyze_line_ops(self, global_line_stats: Dict[int, Any], missing_arcs: Set[Tuple[int, int, int]], executed_arcs: Set[Tuple[int, int, int]]) -> None:
        """Analyze grouped line operations to construct and identify missing and executed boolean vectors."""
        for lineno, stats in global_line_stats.items():
            for decision in stats.get('decisions', []):
                ops = decision['ops']
                decision['missing'] = []
                decision['executed'] = []
                decision['conditions'] = len(ops)

                executed_paths = BooleanVectorEvaluator.reconstruct_executed_paths(ops, executed_arcs)

                for p, out in executed_paths:
                    decision['executed'].append({'vector': list(p), 'result': out})

                decision['missing'].extend(BooleanVectorEvaluator.find_missing_condition_arcs(ops, missing_arcs))

    def _evaluate_outcomes(self, code_obj: types.CodeType, missing_arcs: Set[Tuple[int, int, int]], executed_arcs: Set[Tuple[int, int, int]]) -> Dict[int, Any]:
        return self.map_missing_arcs(code_obj, missing_arcs, executed_arcs)

    def post_process(self, stats: Dict[str, Any], static_source: Any, executed_data: Set[Any]) -> None:
        """
        Hook called after calculate_stats to refine global statistics based on
        actual conditions rather than raw bytecode arcs.
        """
        code_obj = static_source
        if not code_obj or not isinstance(code_obj, types.CodeType):
            return

        missing_outcomes = self._evaluate_outcomes(code_obj, stats['missing'], executed_data)
        OutcomeFormatter.format_global_stats(stats, missing_outcomes)
