from typing import Dict, Any

# Type aliases for clarity
CoverageStats = Dict[str, Any]
FileResults = Dict[str, CoverageStats]
AnalysisResults = Dict[str, FileResults]

class BaseReporter:
    """
    Abstract base class for all coverage reporters.
    Enforces a consistent interface for the strategy pattern.
    """
    def generate(self, results: AnalysisResults, project_root: str) -> None:
        """
        Generate the report based on analysis results.

        Args:
            results (dict): The coverage analysis data.
            project_root (str): The root directory of the project.
        """
        raise NotImplementedError
