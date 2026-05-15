from collections import defaultdict
from typing import Dict, Any
from enum import Enum


class TraceDataType(str, Enum):
    LINES = 'lines'
    ARCS = 'arcs'
    INSTRUCTION_ARCS = 'instruction_arcs'
    DECISION_PATHS = 'decision_paths'


class TraceContainer:
    """
    Encapsulates coverage data storage.
    """
    def __init__(self) -> None:
        self._data: Dict[str, Any] = {
            TraceDataType.LINES: defaultdict(lambda: defaultdict(set)),
            TraceDataType.ARCS: defaultdict(lambda: defaultdict(set)),
            TraceDataType.INSTRUCTION_ARCS: defaultdict(lambda: defaultdict(set)),
            TraceDataType.DECISION_PATHS: defaultdict(lambda: defaultdict(set))
        }

    def add_line(self, filename: str, context_id: int, lineno: int) -> None:
        self._data[TraceDataType.LINES][filename][context_id].add(lineno)

    def add_arc(self, filename: str, context_id: int, start: int, end: int) -> None:
        self._data[TraceDataType.ARCS][filename][context_id].add((start, end))

    def add_instruction_arc(self, filename: str, context_id: int, code_id: int, start: int, end: int) -> None:
        self._data[TraceDataType.INSTRUCTION_ARCS][filename][context_id].add((code_id, start, end))

    def add_decision_path(self, filename: str, context_id: int, code_id: int, path: tuple) -> None:
        self._data[TraceDataType.DECISION_PATHS][filename][context_id].add((code_id, path))

    def __getitem__(self, key: str) -> Any:
        return self._data[key]
