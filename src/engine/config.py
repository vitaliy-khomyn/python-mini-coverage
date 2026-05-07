from dataclasses import dataclass, field
from typing import Set, Dict, List
from enum import Enum


class ReporterType(str, Enum):
    CONSOLE = 'console'
    HTML = 'html'
    XML = 'xml'
    JSON = 'json'


# Default patterns for files and directories to omit from coverage.
# This helps automatically exclude virtual environments and system libraries.
DEFAULT_OMIT_PATTERNS = {
    '*/site-packages/*',
    '*/dist-packages/*',
    '.venv/*',
    'venv/*',
    '*/.local/lib/python*/*',
    '*/Python*/lib/site-packages/*',
    '*/python*/lib/site-packages/*',
}


@dataclass
class CoverageConfig:
    omit: Set[str] = field(default_factory=lambda: DEFAULT_OMIT_PATTERNS.copy())
    include: Set[str] = field(default_factory=set)
    source: Set[str] = field(default_factory=set)
    branch: bool = False
    concurrency: str = 'thread'
    exclude_lines: Set[str] = field(default_factory=set)
    data_file: str = '.coverage.db'
    paths: Dict[str, List[str]] = field(default_factory=dict)
    reporters: List[str] = field(default_factory=lambda: [ReporterType.CONSOLE.value, ReporterType.HTML.value])
    report_metrics: List[str] = field(default_factory=list)
