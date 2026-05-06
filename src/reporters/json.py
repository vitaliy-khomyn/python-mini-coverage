import os
import json
import logging
import time

from typing import Any

from .base import BaseReporter, AnalysisResults
from .registry import get_active_metrics


class JsonReporter(BaseReporter):
    """
    Generates a JSON report for programmatic consumption.
    """

    def __init__(self, config: Any = None, output_file: str = "coverage.json") -> None:
        super().__init__(config)
        self.logger = logging.getLogger(__name__)
        self.output_file = output_file

    def generate(self, results: AnalysisResults, project_root: str) -> None:
        self.logger.info(f"Generating JSON report to {self.output_file}...")

        active_metrics = {m.name for m in get_active_metrics(self.config)}
        serializable_results = {}

        for filename, metrics in results.items():
            rel_name = os.path.relpath(filename, project_root)
            file_metrics = {}

            for metric_name, stats in metrics.items():
                if metric_name not in active_metrics:
                    continue

                file_metrics[metric_name] = {
                    'pct': stats['pct'],
                    'ratio': stats.get('ratio', "0/0"),
                    'missing': sorted(list(stats['missing'])),
                    'executed': sorted(list(stats['executed'])),
                    'possible': sorted(list(stats['possible']))
                }

                if 'missing_outcomes' in stats:
                    file_metrics[metric_name]['missing_outcomes'] = stats['missing_outcomes']

            if file_metrics:
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
