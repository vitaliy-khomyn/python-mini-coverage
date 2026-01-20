import types
import collections
from typing import Set, Tuple, Optional, Dict, Any, List
from .base import CoverageMetric
from .cfg import ControlFlowGraph


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

    def _get_branch_labels(self, opname: str) -> Tuple[str, str]:
        """Returns (jump_label, fallthrough_label) for a boolean opcode."""
        jump_val = "True" if "TRUE" in opname else "False"
        fall_val = "False" if jump_val == "True" else "True"
        return jump_val, fall_val

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
        cfg = ControlFlowGraph(co)
        code_id = co.co_firstlineno

        for i, instr in enumerate(cfg.instructions):
            # instructions relevant for boolean logic
            # includes python 3.11+ directional variants
            is_bool_jump = instr.opname in self.BOOL_OPS

            if is_bool_jump:
                # 1. target arc (Jump Taken)
                target = int(instr.argval)
                arcs.add((code_id, instr.offset, target))

                # 2. fallthrough arc (Jump Not Taken)
                # ensure we don't go out of bounds
                next_offset = self._find_next_instr(cfg.instructions, i)
                if next_offset is not None:
                    arcs.add((code_id, instr.offset, next_offset))

        # recurse
        for const in co.co_consts:
            if isinstance(const, types.CodeType):
                self._analyze_boolean_jumps(const, arcs)

    def map_missing_arcs(self, code_obj: types.CodeType, missing_arcs: Set[Tuple[int, int, int]]) -> Dict[int, Any]:
        """
        Map missing bytecode arcs to source line numbers with human-readable labels.
        Returns: {lineno: {'missing': [{'vector': '...', 'terminal': bool}], 'ratio': '3/4'}}
        """
        # We will accumulate stats per line across all code objects (handling lambdas etc)
        # Structure: lineno -> {'total': int, 'missing': [str]}
        global_line_stats = collections.defaultdict(lambda: {'total': 0, 'missing': []})

        if not missing_arcs or not code_obj:
            return {}

        def _visit_code(co):
            # Recurse into nested code objects (lambdas, comprehensions, inner functions)
            for const in co.co_consts:
                if isinstance(const, types.CodeType):
                    _visit_code(const)

            code_id = co.co_firstlineno
            try:
                cfg = ControlFlowGraph(co)
            except Exception:
                return

            # 1. Collect boolean instructions for this code object, grouped by line
            # We need a reliable offset-to-line mapping
            offset_to_line = {}
            if hasattr(co, 'co_lines'):
                for start, end, line in co.co_lines():
                    if line is not None:
                        for off in range(start, end, 2):
                            offset_to_line[off] = line

            line_ops = collections.defaultdict(list)
            for i, instr in enumerate(cfg.instructions):
                if instr.opname in self.BOOL_OPS:
                    lineno = offset_to_line.get(instr.offset, co.co_firstlineno)
                    if lineno and lineno > 0:
                        # We need next_offset to identify the fallthrough arc
                        next_offset = None
                        next_offset = self._find_next_instr(cfg.instructions, i)

                        line_ops[lineno].append({
                            'instr': instr,
                            'next_offset': next_offset
                        })

            # 2. Analyze each line's boolean logic to construct vectors
            for lineno, ops in line_ops.items():
                # Sort by offset to establish evaluation order
                ops.sort(key=lambda x: x['instr'].offset)

                # Calculate total terminal paths for this line
                # For a sequence of N boolean ops, there are N+1 terminal paths.
                global_line_stats[lineno]['total'] += len(ops) + 1

                for i, op_data in enumerate(ops):
                    instr = op_data['instr']
                    next_offset = op_data['next_offset']

                    # Determine values
                    jump_val, fall_val = self._get_branch_labels(instr.opname)

                    # Construct "Prefix": The path required to reach this condition.
                    # We assume sequential evaluation: to reach op[i], we must have fallen through op[0]...op[i-1]
                    prefix = []
                    for prev_op in ops[:i]:
                        _, prev_fall_val = self._get_branch_labels(prev_op['instr'].opname)
                        prefix.append(prev_fall_val)

                    # Suffix length (remaining conditions on this line)
                    suffix_len = len(ops) - 1 - i

                    # Check Jump Arc (Short-circuit path)
                    target = int(instr.argval)
                    jump_key = (code_id, instr.offset, target)
                    if jump_key in missing_arcs:
                        # If we jump, we skip the suffix. Represent skipped as "-"
                        vector = prefix + [jump_val] + ["-"] * suffix_len
                        global_line_stats[lineno]['missing'].append({
                            'vector': vector,
                            'terminal': True
                        })

                    # Check Fallthrough Arc (Continue path)
                    if next_offset is not None:
                        fall_key = (code_id, instr.offset, next_offset)
                        if fall_key in missing_arcs:
                            vector = prefix + [fall_val] + ["..."] * suffix_len
                            global_line_stats[lineno]['missing'].append({
                                'vector': vector,
                                'terminal': (i == len(ops) - 1)
                            })

        _visit_code(code_obj)

        # Format the result
        result = {}
        for lineno, stats in global_line_stats.items():
            # Calculate clean_missing regardless of whether it's empty
            clean_missing = []
            if stats['missing']:
                # Filter redundant intermediate vectors (e.g. remove "True, ..." if "True, False" exists)
                raw_items = stats['missing']
                indices_to_remove = set()

                for i, item_a in enumerate(raw_items):
                    if item_a['terminal']:
                        continue

                    vec_a = item_a['vector']
                    # Find prefix before "..."
                    try:
                        stop_idx = vec_a.index("...")
                        prefix_a = vec_a[:stop_idx]
                    except ValueError:
                        prefix_a = vec_a

                    # Check if extended by any other vector
                    for j, item_b in enumerate(raw_items):
                        if i == j: continue
                        vec_b = item_b['vector']
                        if len(vec_b) >= len(prefix_a) and vec_b[:len(prefix_a)] == prefix_a:
                            indices_to_remove.add(i)
                            break

                for i, item in enumerate(raw_items):
                    if i not in indices_to_remove:
                        clean_missing.append({
                            'vector': ", ".join(item['vector']),
                            'terminal': item['terminal']
                        })

            covered = stats['total'] - len(clean_missing)
            ratio = f"{covered}/{stats['total']}"
            result[lineno] = {
                'missing': clean_missing,
                'ratio': ratio,
                'covered': covered,
                'total': stats['total']
            }

        return result
