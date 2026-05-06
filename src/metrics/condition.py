import ast
import collections
import dis
import sys
import types

from typing import Set, Tuple, Optional, Dict, Any, List

from .base import CoverageMetric, StaticSourceType
from .boolean_vector import BooleanVectorEvaluator
from ..engine.trace_data import TraceDataType


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

    def get_name(self) -> str:
        return "Condition"

    def get_required_static_source(self) -> StaticSourceType:
        return StaticSourceType.CODE_OBJECT

    def get_required_dynamic_data(self) -> TraceDataType:
        return TraceDataType.INSTRUCTION_ARCS

    def set_ast(self, tree: ast.AST) -> None:
        self.valid_condition_lines = set()
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

                if hasattr(self, 'valid_condition_lines') and lineno not in self.valid_condition_lines:
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

        # Format the result
        result = {}
        for lineno, stats in global_line_stats.items():
            clean_missing = self._filter_redundant_vectors(stats.get('missing', []))
            covered = stats['total'] - len(clean_missing)
            ratio = f"{covered}/{stats['total']}"
            result[lineno] = {
                'missing': clean_missing,
                'executed': stats.get('executed', []),
                'conditions': stats.get('conditions', 0),
                'ratio': ratio,
                'covered': covered,
                'total': stats['total']
            }
        return result

    def _collect_line_ops(self, co: types.CodeType, line_stats: Dict[int, Any]) -> None:
        """Recursively visit code objects and group boolean instructions by line number."""
        for const in co.co_consts:
            if isinstance(const, types.CodeType):
                self._collect_line_ops(const, line_stats)

        try:
            instructions = self._get_instructions(co)
        except Exception:
            return

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
                    if hasattr(self, 'valid_condition_lines') and lineno not in self.valid_condition_lines:
                        continue

                    line_ops[lineno].append({
                        'instr': instr,
                        'next_offset': self._find_next_instr(instructions, i),
                        'code_id': co.co_firstlineno
                    })

        for lineno, ops in line_ops.items():
            ops.sort(key=lambda x: x['instr'].offset)
            line_stats[lineno].setdefault('ops', []).extend(ops)
            line_stats[lineno].setdefault('total', 0)
            line_stats[lineno]['total'] += len(ops) + 1

    def _analyze_line_ops(self, global_line_stats: Dict[int, Any], missing_arcs: Set[Tuple[int, int, int]], executed_arcs: Set[Tuple[int, int, int]]) -> None:
        """Analyze grouped line operations to construct and identify missing and executed boolean vectors."""
        for lineno, stats in global_line_stats.items():
            ops = stats.get('ops', [])
            stats['missing'] = []
            stats['executed'] = []
            stats['conditions'] = len(ops)

            executed_paths = BooleanVectorEvaluator.reconstruct_executed_paths(ops, executed_arcs)

            for p, out in executed_paths:
                stats['executed'].append({'vector': list(p), 'result': out})

            stats['missing'].extend(BooleanVectorEvaluator.find_missing_condition_arcs(ops, missing_arcs))

    def _filter_redundant_vectors(self, raw_items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
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
