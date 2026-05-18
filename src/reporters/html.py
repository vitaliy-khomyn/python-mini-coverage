import os
import html
import collections
import tokenize
from pathlib import Path

from typing import Any, Dict, List, Optional

from . import templates
from .base import BaseReporter, AnalysisResults, FileResults
from .registry import get_active_metrics


class HtmlReporter(BaseReporter):
    """
    Generates a static HTML website visualizing coverage.
    """

    def __init__(self, config: Any = None, output_dir: str = "htmlcov") -> None:
        super().__init__(config)
        self.output_dir = output_dir

    def generate(self, results: AnalysisResults, project_root: str) -> None:
        out_path = Path(self.output_dir)
        out_path.mkdir(parents=True, exist_ok=True)

        self.logger.info(f"Generating HTML report in {self.output_dir}...")
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
                poss, exc = m.formatter.get_totals(metric_data)
                totals[key]['possible'] += poss
                totals[key]['missing'] += (poss - exc)

            if not has_statement_data:
                continue

            try:
                rel_name = str(Path(filename).relative_to(Path(project_root)))
            except ValueError:
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

        with open(Path(self.output_dir) / "index.html", "w", encoding="utf-8") as f:
            f.write(html_content)

    def _generate_file_report(self, filename: str, data: FileResults, project_root: str) -> None:
        try:
            rel_name = str(Path(filename).relative_to(Path(project_root)))
        except ValueError:
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
                anns = m.formatter.format_html(stats)
                for lineno, ann_list in anns.items():
                    line_annotations[lineno].extend(ann_list)

        try:
            with tokenize.open(filename) as f:
                source_lines = f.readlines()
        except (OSError, UnicodeDecodeError):
            source_lines = ["Error reading source file."]

        code_html = ""
        for i, line in enumerate(source_lines):
            lineno = i + 1
            css_class = ""
            toggle_text: Optional[str] = None
            inline_detail: Optional[str] = None
            details_html = None

            if lineno in executed_lines:
                css_class = "hit"
            elif lineno in missing_lines:
                css_class = "miss"

            if lineno in line_annotations:
                anns = line_annotations[lineno]
                is_simple = len(anns) == 1 and '<table' not in anns[0].lower() and '<br' not in anns[0].lower()

                if is_simple:
                    inline_detail = anns[0]
                    if css_class == "hit":
                        css_class = "partial"
                else:
                    if css_class == "hit":
                        css_class = "partial"
                    toggle_text = f"{len(anns)} Missing Details"
                    list_items = "<hr class='annotation-divider'>".join([f"<div style='margin-bottom: 5px;'>{a}</div>" for a in anns])
                    details_html = f"<div class='annotation-list'>{list_items}</div>"

            line_content = html.escape(line.rstrip())
            code_html += templates.render_code_line(lineno, line_content, css_class, toggle_text, details_html, inline_detail)

        html_content = templates.render_file(html.escape(rel_name), code_html)

        with open(Path(self.output_dir) / out_name, "w", encoding="utf-8") as f:
            f.write(html_content)

    def _sanitize_filename(self, path: str) -> str:
        return path.replace("\\", "_").replace("/", "_").replace(".", "_")
