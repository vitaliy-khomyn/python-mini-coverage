from dataclasses import dataclass, field
from typing import Set, Dict, List


@dataclass
class CoverageConfig:
    omit: Set[str] = field(default_factory=set)
    include: Set[str] = field(default_factory=set)
    source: Set[str] = field(default_factory=set)
    branch: bool = False
    concurrency: str = 'thread'
    exclude_lines: Set[str] = field(default_factory=set)
    data_file: str = '.coverage.db'
    paths: Dict[str, List[str]] = field(default_factory=dict)
    reporters: List[str] = field(default_factory=lambda: ['console', 'html', 'xml', 'json'])
