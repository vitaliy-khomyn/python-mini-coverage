import os
import html
import collections
from typing import Any, Dict, List
from .base import BaseReporter, AnalysisResults, FileResults
from . import templates
from .registry import get_active_metrics


class HtmlReporter(BaseReporter):
    """
    Generates a static HTML website visualizing coverage.
    """

    def __init__(self, config: Any = None, output_dir: str = "htmlcov") -> None:
        super().__init__(config)
        self.output_dir = output_dir

    def generate(self, results: AnalysisResults, project_root: str) -> None:
        if not os.path.exists(self.output_dir):
            os.makedirs(self.output_dir)

        print(f"Generating HTML report in {self.output_dir}...")
        self._generate_index(results, project_root)

        for filename, data in results.items():
            self._generate_file_report(filename, data, project_root)

    def _generate_index(self, results: AnalysisResults, project_root: str) -> None:
        active_metrics = get_active_metrics(self.config)
        totals = {m.key: {'possible': 0, 'missing': 0} for m in active_metrics}

        rows = ""
        for filename in sorted(results.keys()):
            # Collect data for all metrics for the current file
            file_metrics_list = []
            has_statement_data = False
            for m in active_metrics:
                metric_data = results[filename].get(m.name, {})
                metric_data.setdefault('pct', 0)
                metric_data.setdefault('ratio', "0/0")
                file_metrics_list.append(metric_data)

                if m.name == 'Statement' and metric_data.get('possible'):
                    has_statement_data = True

                # Aggregate totals
                key = m.key
                if 'total_possible' in metric_data:
                    totals[key]['possible'] += metric_data['total_possible']
                    totals[key]['missing'] += metric_data['total_missing']
                else:
                    totals[key]['possible'] += len(metric_data.get('possible', []))
                    totals[key]['missing'] += len(metric_data.get('missing', []))

            if not has_statement_data:
                continue

            rel_name = os.path.relpath(filename, project_root)
            file_html_link = f"{self._sanitize_filename(rel_name)}.html"

            rows += templates.render_index_row(
                file_html_link,
                html.escape(rel_name),
                file_metrics_list
            )

        # calculate total percentages
        def calc_pct(poss: int, miss: int) -> float:
            if poss == 0:
                return 100.0
            return ((poss - miss) / poss) * 100.0

        def calc_ratio(poss: int, miss: int) -> str:
            return f"{poss - miss}/{poss}"

        total_stats = []
        for m in active_metrics:
            key = m.key
            poss, miss = totals[key]['possible'], totals[key]['missing']
            total_stats.append({
                'display': m.html_display,
                'pct': calc_pct(poss, miss),
                'ratio': calc_ratio(poss, miss)
            })

        html_content = templates.render_index([m.html_display for m in active_metrics], total_stats, rows)

        with open(os.path.join(self.output_dir, "index.html"), "w", encoding="utf-8") as f:
            f.write(html_content)

    def _get_html_annotations(self, metric_name: str, stats: Dict[str, Any]) -> Dict[int, List[str]]:
        annotations: Dict[int, List[str]] = collections.defaultdict(list)
        missing = stats.get('missing', set())
        if not missing and metric_name != 'Condition':
            return annotations

        if metric_name == 'Branch':
            missing_branches: Dict[int, List[int]] = collections.defaultdict(list)
            for start, end in missing:
                missing_branches[start].append(end)
            for start, targets in missing_branches.items():
                targets_str = ", ".join(map(str, targets))
                annotations[start].append(f"Missed branch to: {targets_str}")
        elif metric_name == 'Function':
            for name, def_line, _ in missing:
                annotations[def_line].append(f"Function '{html.escape(name)}' was not called")
        elif metric_name == 'Loop':
            for start, end in missing:
                if "Missed loop path(s)" not in annotations[start]:
                    annotations[start].append("Missed loop path(s)")
        elif metric_name == 'Class':
            for name, def_line, _ in missing:
                annotations[def_line].append(f"Class '{html.escape(name)}' was not instantiated")
        elif metric_name == 'Call-Site':
            calls_by_line: Dict[int, List[str]] = collections.defaultdict(list)
            for name, lineno in missing:
                calls_by_line[lineno].append(name)
            for lineno, names in calls_by_line.items():
                annotations[lineno].append(f"Missed call to: {html.escape(', '.join(names))}")
        elif metric_name == 'Exception':
            for lineno in missing:
                annotations[lineno].append("Missed exception handler")
        elif metric_name == 'Condition':
            missing_outcomes = stats.get('missing_outcomes', {})
            for lineno, cond_info in missing_outcomes.items():
                if isinstance(cond_info, dict) and 'ratio' in cond_info and cond_info.get('missing'):
                    rows = ""
                    for item in cond_info['missing']:
                        vec = item.get('vector', str(item))
                        rows += f"<tr><td>{html.escape(vec)}</td></tr>"
                    table = f"<strong>Condition Coverage: {cond_info['ratio']}</strong>" \
                            f"<table class='condition-table'><tbody>{rows}</tbody></table>"
                    annotations[lineno].append(table)

        return dict(annotations)

    def _generate_file_report(self, filename: str, data: FileResults, project_root: str) -> None:
        rel_name = os.path.relpath(filename, project_root)
        out_name = f"{self._sanitize_filename(rel_name)}.html"

        stmt_data = data.get('Statement')
        if not stmt_data:
            return

        executed_lines = stmt_data.get('executed', set())
        missing_lines = stmt_data.get('missing', set())

        # Aggregate all HTML annotations uniformly
        line_annotations: Dict[int, List[str]] = collections.defaultdict(list)
        active_metrics = get_active_metrics(self.config)
        for m in active_metrics:
            stats = data.get(m.name)
            if stats:
                anns = self._get_html_annotations(m.name, stats)
                for lineno, ann_list in anns.items():
                    line_annotations[lineno].extend(ann_list)

        try:
            with open(filename, 'r', encoding='utf-8') as f:
                source_lines = f.readlines()
        except Exception:
            source_lines = ["Error reading source file."]

        code_html = ""
        for i, line in enumerate(source_lines):
            lineno = i + 1
            css_class = ""
            details_html = None
            toggle_text = None

            if lineno in executed_lines:
                css_class = "hit"
            elif lineno in missing_lines:
                css_class = "miss"

            if lineno in line_annotations:
                if css_class == "hit":
                    css_class = "partial"
                anns = line_annotations[lineno]
                toggle_text = f"{len(anns)} Missing Details"
                list_items = "".join([f"<div style='margin-bottom: 5px;'>{a}</div>" for a in anns])
                details_html = f"<div class='annotation-list'>{list_items}</div>"

            line_content = html.escape(line.rstrip())
            code_html += templates.render_code_line(lineno, line_content, css_class, toggle_text, details_html)

        html_content = templates.render_file(html.escape(rel_name), code_html)

        with open(os.path.join(self.output_dir, out_name), "w", encoding="utf-8") as f:
            f.write(html_content)

    def _sanitize_filename(self, path: str) -> str:
        return path.replace(os.sep, "_").replace(".", "_")
