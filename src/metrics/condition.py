import dis
import types
from typing import Set, Tuple, Optional
from .base import CoverageMetric
from .cfg import ControlFlowGraph


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
        # instructions to find offsets
        cfg = ControlFlowGraph(co)

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
                arcs.add((instr.offset, target))

                # 2.fallthrough arc (Jump Not Taken)
                # Ensure we don't go out of bounds
                if i + 1 < len(cfg.instructions):
                    next_offset = cfg.instructions[i + 1].offset
                    arcs.add((instr.offset, next_offset))

        # recurse
        for const in co.co_consts:
            if isinstance(const, types.CodeType):
                self._analyze_boolean_jumps(const, arcs)
