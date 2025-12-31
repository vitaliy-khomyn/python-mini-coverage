import os
import json
import time
import logging
from .base import BaseReporter, AnalysisResults


class JsonReporter(BaseReporter):
    """
    Generates a JSON report for programmatic consumption.
    """

    def __init__(self, output_file: str = "coverage.json") -> None:
        self.logger = logging.getLogger(__name__)
        self.output_file = output_file

    def generate(self, results: AnalysisResults, project_root: str) -> None:
        self.logger.info(f"Generating JSON report to {self.output_file}...")

        serializable_results = {}
        for filename, metrics in results.items():
            rel_name = os.path.relpath(filename, project_root)
            file_metrics = {}

            for metric_name, stats in metrics.items():
                file_metrics[metric_name] = {
                    'pct': stats['pct'],
                    'missing': sorted(list(stats['missing'])),
                    'executed': sorted(list(stats['executed'])),
                    'possible': sorted(list(stats['possible']))
                }
            serializable_results[rel_name] = file_metrics

        final_report = {
            'meta': {
                'timestamp': time.time(),
                'project_root': project_root
            },
            'files': serializable_results
        }

        with open(self.output_file, 'w', encoding='utf-8') as f:
            json.dump(final_report, f, indent=4)
