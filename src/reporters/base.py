from abc import ABC
import logging
from typing import Dict, Any

# type aliases for clarity
CoverageStats = Dict[str, Any]
FileResults = Dict[str, CoverageStats]
AnalysisResults = Dict[str, FileResults]


class BaseReporter(ABC):
    """
    Abstract base class for all coverage reporters.
    Enforces a consistent interface for the strategy pattern.
    """
    def __init__(self, config: Any = None):
        self.config = config
        self.logger = logging.getLogger(self.__class__.__name__)

    def generate(self, results: AnalysisResults, project_root: str) -> None:
        """
        Generate the report based on analysis results.

        Args:
            results (dict): The coverage analysis data.
            project_root (str): The root directory of the project.
        """
        raise NotImplementedError
