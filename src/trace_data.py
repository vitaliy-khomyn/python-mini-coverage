from collections import defaultdict
from typing import Dict, Any


class TraceContainer:
    """
    Encapsulates coverage data storage.
    """
    def __init__(self) -> None:
        self._data: Dict[str, Any] = {
            'lines': defaultdict(lambda: defaultdict(set)),
            'arcs': defaultdict(lambda: defaultdict(set)),
            'instruction_arcs': defaultdict(lambda: defaultdict(set))
        }

    def add_line(self, filename: str, context_id: int, lineno: int) -> None:
        self._data['lines'][filename][context_id].add(lineno)

    def add_arc(self, filename: str, context_id: int, start: int, end: int) -> None:
        self._data['arcs'][filename][context_id].add((start, end))

    def add_instruction_arc(self, filename: str, context_id: int, start: int, end: int) -> None:
        self._data['instruction_arcs'][filename][context_id].add((start, end))

    def __getitem__(self, key: str) -> Any:
        return self._data[key]
