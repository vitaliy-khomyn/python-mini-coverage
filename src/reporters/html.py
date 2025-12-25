import os
import html
import collections
from .base import BaseReporter, AnalysisResults, FileResults
from . import templates


class HtmlReporter(BaseReporter):
    """
    Generates a static HTML website visualizing coverage.
    """

    def __init__(self, output_dir: str = "htmlcov") -> None:
        self.output_dir = output_dir

    def generate(self, results: AnalysisResults, project_root: str) -> None:
        if not os.path.exists(self.output_dir):
            os.makedirs(self.output_dir)

        print(f"Generating HTML report in {self.output_dir}...")
        self._generate_index(results, project_root)

        for filename, data in results.items():
            self._generate_file_report(filename, data, project_root)

    def _generate_index(self, results: AnalysisResults, project_root: str) -> None:
        total_stmts = 0
        total_miss = 0

        rows = ""
        for filename in sorted(results.keys()):
            stmt = results[filename].get('Statement')
            if not stmt:
                continue

            possible = len(stmt['possible'])
            miss = len(stmt['missing'])
            total_stmts += possible
            total_miss += miss

            pct = stmt['pct']

            rel_name = os.path.relpath(filename, project_root)
            file_html_link = f"{self._sanitize_filename(rel_name)}.html"

            rows += templates.render_index_row(
                file_html_link,
                html.escape(rel_name),
                possible,
                miss,
                pct
            )

        total_pct = 100.0
        if total_stmts > 0:
            total_pct = ((total_stmts - total_miss) / total_stmts) * 100

        html_content = templates.render_index(total_pct, rows)

        with open(os.path.join(self.output_dir, "index.html"), "w") as f:
            f.write(html_content)

    def _generate_file_report(self, filename: str, data: FileResults, project_root: str) -> None:
        rel_name = os.path.relpath(filename, project_root)
        out_name = f"{self._sanitize_filename(rel_name)}.html"

        stmt_data = data.get('Statement')
        if not stmt_data:
            return

        executed_lines = stmt_data['executed']
        missing_lines = stmt_data['missing']

        branch_data = data.get('Branch')
        missing_branches = collections.defaultdict(list)
        if branch_data:
            for start, end in branch_data['missing']:
                missing_branches[start].append(end)

        try:
            with open(filename, 'r', encoding='utf-8') as f:
                source_lines = f.readlines()
        except Exception:
            source_lines = ["Error reading source file."]

        code_html = ""
        for i, line in enumerate(source_lines):
            lineno = i + 1
            css_class = ""
            annotation = ""

            if lineno in executed_lines:
                css_class = "hit"
            elif lineno in missing_lines:
                css_class = "miss"

            if lineno in missing_branches:
                targets = missing_branches[lineno]
                if css_class == "hit":
                    css_class = "partial"

                targets_str = ", ".join(map(str, targets))
                annotation = f"<span class='annotate'>Missed branch to: {targets_str}</span>"

            line_content = html.escape(line.rstrip())
            code_html += templates.render_code_line(lineno, line_content, css_class, annotation)

        html_content = templates.render_file(html.escape(rel_name), code_html)

        with open(os.path.join(self.output_dir, out_name), "w") as f:
            f.write(html_content)

    def _sanitize_filename(self, path: str) -> str:
        return path.replace(os.sep, "_").replace(".", "_")