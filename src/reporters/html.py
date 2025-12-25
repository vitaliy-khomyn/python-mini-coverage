import os
import html
import collections
from .base import BaseReporter, AnalysisResults, FileResults


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

        rows = []
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

            rows.append(f"""
            <tr>
                <td><a href="{file_html_link}">{html.escape(rel_name)}</a></td>
                <td>{possible}</td>
                <td>{miss}</td>
                <td>{pct:.0f}%</td>
            </tr>
            """)

        total_pct = 100.0
        if total_stmts > 0:
            total_pct = ((total_stmts - total_miss) / total_stmts) * 100

        html_content = f"""
        <html>
        <head>
            <title>Coverage Report</title>
            <style>
                body {{ font-family: sans-serif; padding: 20px; }}
                table {{ border-collapse: collapse; width: 100%; }}
                th, td {{ border: 1px solid #ddd; padding: 8px; text-align: left; }}
                th {{ background-color: #f2f2f2; }}
                .header {{ margin-bottom: 20px; }}
            </style>
        </head>
        <body>
            <div class="header">
                <h1>Coverage Report</h1>
                <p>Total Coverage: <strong>{total_pct:.0f}%</strong></p>
            </div>
            <table>
                <thead>
                    <tr>
                        <th>File</th>
                        <th>Statements</th>
                        <th>Missed</th>
                        <th>Coverage</th>
                    </tr>
                </thead>
                <tbody>
                    {"".join(rows)}
                </tbody>
            </table>
        </body>
        </html>
        """

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

        code_html = []
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
            code_html.append(f"""
            <div class="line {css_class}">
                <span class="lineno">{lineno}</span>
                <pre>{line_content}</pre>
                {annotation}
            </div>
            """)

        html_content = f"""
        <html>
        <head>
            <title>{html.escape(rel_name)} - Coverage</title>
            <style>
                body {{ font-family: monospace; }}
                .line {{ display: flex; }}
                .lineno {{ width: 50px; color: #999; border-right: 1px solid #ddd; padding-right: 10px; margin-right: 10px; text-align: right; user-select: none; }}
                pre {{ margin: 0; }}
                .hit {{ background-color: #dff0d8; }}
                .miss {{ background-color: #f2dede; }}
                .partial {{ background-color: #fcf8e3; }}
                .annotate {{ color: #a94442; font-size: 0.8em; margin-left: 20px; font-style: italic; }}
            </style>
        </head>
        <body>
            <h3>{html.escape(rel_name)}</h3>
            {"".join(code_html)}
        </body>
        </html>
        """

        with open(os.path.join(self.output_dir, out_name), "w") as f:
            f.write(html_content)

    def _sanitize_filename(self, path: str) -> str:
        return path.replace(os.sep, "_").replace(".", "_")
