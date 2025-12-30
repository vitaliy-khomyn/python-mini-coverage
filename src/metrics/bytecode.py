import types
from typing import Set, Tuple, Optional
from .base import CoverageMetric
from .cfg import ControlFlowGraph


class BytecodeControlFlow(CoverageMetric):
    """
    Analyzes Python bytecode to determine control flow jumps.
    Now uses a full Control Flow Graph (CFG) builder.
    """
    def get_name(self) -> str:
        return "Bytecode"

    def get_possible_elements(self, code_obj: Optional[types.CodeType], ignored_lines: Optional[Set[int]] = None) -> Set[Tuple[int, int]]:
        if not code_obj:
            return set()

        jumps: Set[Tuple[int, int]] = set()
        self._analyze_code_object(code_obj, jumps)
        return jumps

    def _analyze_code_object(self, co: types.CodeType, jumps: Set[Tuple[int, int]]) -> None:
        # build CFG for the current code object
        cfg = ControlFlowGraph(co)
        jumps.update(cfg.get_jumps())

        for const in co.co_consts:
            if isinstance(const, types.CodeType):
                self._analyze_code_object(const, jumps)
