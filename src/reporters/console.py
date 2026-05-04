import os
from typing import Any, List
from .base import BaseReporter, AnalysisResults
from .registry import get_active_metrics


class ConsoleReporter(BaseReporter):
    """
    Outputs coverage statistics to the standard output.
    """

    def generate(self, results: AnalysisResults, project_root: str) -> None:
        active_metrics = get_active_metrics(self.config)

        headers_list = [f"{'File':<40}"]
        for m in active_metrics:
            headers_list.append(f"{m.console_header:>6}")
        headers_list.append("Missing")

        headers = " | ".join(headers_list)

        print("\n" + "=" * len(headers))
        print(headers)
        print("-" * len(headers))

        for filename in sorted(results.keys()):
            file_data = results[filename]
            if 'Statement' in file_data:
                self._print_row(filename, file_data, active_metrics, project_root)
        print("=" * len(headers))

    def _print_row(self, filename: str, file_data: dict, active_metrics: List[Any], project_root: str) -> None:
        rel_name = os.path.relpath(filename, project_root)
        row_str = f"{rel_name:<40}"
        missing_items = []

        for m in active_metrics:
            metric_data = file_data.get(m.name)
            if metric_data:
                if metric_data.get('possible'):
                    val_str = f"{metric_data['pct']:>5.0f}%"
                else:
                    val_str = "   N/A" if m.name == 'Statement' else "     -"
            else:
                val_str = "     -"

            row_str += f" | {val_str:>6}"
            if metric_data:
                miss_str_metric = m.formatter.format_console(metric_data)
                if miss_str_metric:
                    missing_items.append(miss_str_metric)

        miss_str = "; ".join(missing_items)
        row_str += f" | {miss_str}"
        print(row_str)
