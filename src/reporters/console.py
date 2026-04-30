import os
from typing import Any, List
from .base import BaseReporter, AnalysisResults, CoverageStats
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

    def _format_console_missing(self, metric_name: str, stats: CoverageStats) -> str:
        missing = stats.get('missing', set())
        if not missing:
            return ""

        if metric_name == 'Statement':
            missing_list = sorted(list(missing))
            if len(missing_list) > 5:
                return f"L{missing_list[0]}..L{missing_list[-1]}"
            return f"Lines: {','.join(map(str, missing_list))}"
        elif metric_name == 'Branch':
            arcs_str = [f"{start}->{end}" for start, end in sorted(list(missing))]
            if len(arcs_str) > 3:
                return f"Branches: {len(arcs_str)} missed"
            return f"Br: {', '.join(arcs_str)}"
        elif metric_name == 'Condition':
            return ""
        elif metric_name == 'Function':
            return f"{len(missing)} funcs"
        elif metric_name == 'Loop':
            return f"{len(missing)} loop paths"
        elif metric_name == 'Class':
            return f"{len(missing)} classes"
        elif metric_name == 'Call-Site':
            return f"{len(missing)} calls"
        elif metric_name == 'Exception':
            return f"{len(missing)} exceptions"

        count = len(missing) if isinstance(missing, set) else len(list(missing))
        if count > 0:
            return f"{count} {metric_name.lower()}s"
        return ""

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
                miss_str_metric = self._format_console_missing(m.name, metric_data)
                if miss_str_metric:
                    missing_items.append(miss_str_metric)

        miss_str = "; ".join(missing_items)
        row_str += f" | {miss_str}"
        print(row_str)
