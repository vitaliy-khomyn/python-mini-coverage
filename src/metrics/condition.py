import types
import collections
from typing import Set, Tuple, Optional, Dict, List
from .base import CoverageMetric
from .cfg import ControlFlowGraph


class ConditionCoverage(CoverageMetric):
    """
    MC/DC Implementation.
    Identifies boolean jump instructions and verifies that both outcomes (True/False)
    were executed at the bytecode level.
    """

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

    def _analyze_boolean_jumps(self, co: types.CodeType, arcs: Set[Tuple[int, int, int]]) -> None:
        # instructions to find offsets
        cfg = ControlFlowGraph(co)
        code_id = co.co_firstlineno

        for i, instr in enumerate(cfg.instructions):
            # instructions relevant for boolean logic
            # includes python 3.11+ directional variants
            is_bool_jump = instr.opname in (
                'POP_JUMP_IF_FALSE',
                'POP_JUMP_IF_TRUE',
                'JUMP_IF_FALSE_OR_POP',
                'JUMP_IF_TRUE_OR_POP',
                'POP_JUMP_FORWARD_IF_FALSE',
                'POP_JUMP_FORWARD_IF_TRUE',
                'POP_JUMP_BACKWARD_IF_FALSE',
                'POP_JUMP_BACKWARD_IF_TRUE'
            )

            if is_bool_jump:
                # 1. target arc (Jump Taken)
                target = int(instr.argval)
                arcs.add((code_id, instr.offset, target))

                # 2. fallthrough arc (Jump Not Taken)
                # ensure we don't go out of bounds
                if i + 1 < len(cfg.instructions):
                    next_offset = cfg.instructions[i + 1].offset
                    arcs.add((code_id, instr.offset, next_offset))

        # recurse
        for const in co.co_consts:
            if isinstance(const, types.CodeType):
                self._analyze_boolean_jumps(const, arcs)

    def map_missing_arcs(self, code_obj: types.CodeType, missing_arcs: Set[Tuple[int, int, int]]) -> Dict[int, List[str]]:
        """
        Map missing bytecode arcs to source line numbers with human-readable labels.
        Returns: {lineno: ['True', 'False']}
        """
        missing_map = collections.defaultdict(list)
        if not missing_arcs or not code_obj:
            return dict(missing_map)

        def _visit_code(co):
            for const in co.co_consts:
                if isinstance(const, types.CodeType):
                    _visit_code(const)

            code_id = co.co_firstlineno

            # Build a robust offset-to-line mapping using co_lines() (Python 3.10+)
            offset_to_line = {}
            if hasattr(co, 'co_lines'):
                for start, end, line in co.co_lines():
                    if line is not None:
                        # Bytecode instructions are 2 bytes
                        for off in range(start, end, 2):
                            offset_to_line[off] = line

            # Use CFG to ensure consistent instruction parsing with _analyze_boolean_jumps
            try:
                cfg = ControlFlowGraph(co)
            except Exception:
                return

            for i, instr in enumerate(cfg.instructions):
                # Lookup line number for this instruction's offset
                lineno = offset_to_line.get(instr.offset, co.co_firstlineno)

                if instr.opname in ('POP_JUMP_IF_FALSE', 'POP_JUMP_IF_TRUE', 'JUMP_IF_FALSE_OR_POP', 'JUMP_IF_TRUE_OR_POP', 'POP_JUMP_FORWARD_IF_FALSE', 'POP_JUMP_FORWARD_IF_TRUE', 'POP_JUMP_BACKWARD_IF_FALSE', 'POP_JUMP_BACKWARD_IF_TRUE'):
                    jump_val = "True" if "TRUE" in instr.opname else "False"
                    fall_val = "False" if jump_val == "True" else "True"

                    # Filter out invalid line numbers (0, negative, or None)
                    if lineno is None or lineno <= 0:
                        continue

                    # Check jump target
                    target = int(instr.argval)
                    jump_key = (code_id, instr.offset, target)

                    if jump_key in missing_arcs:
                        missing_map[lineno].append(jump_val)

                    # Check fallthrough
                    if i + 1 < len(cfg.instructions):
                        next_offset = cfg.instructions[i+1].offset
                        fall_key = (code_id, instr.offset, next_offset)

                        if fall_key in missing_arcs:
                            missing_map[lineno].append(fall_val)

        _visit_code(code_obj)
        return dict(missing_map)
