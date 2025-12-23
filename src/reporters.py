import os
import html
import json
import time
import collections
import xml.etree.ElementTree as ET
from typing import Dict, Any, Optional, List, Union

# type aliases for clarity
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


class ConsoleReporter(BaseReporter):
    """
    Outputs coverage statistics to the standard output.
    """

    def generate(self, results: AnalysisResults, project_root: str) -> None:
        print("\n" + "=" * 100)
        headers = f"{'File':<25} | {'Stmt Cov':<9} | {'Branch Cov':<11} | {'Missing'}"
        print(headers)
        print("-" * 100)

        for filename in sorted(results.keys()):
            file_data = results[filename]
            stmt_data = file_data.get('Statement')
            branch_data = file_data.get('Branch')

            if stmt_data:
                self._print_row(filename, stmt_data, branch_data, project_root)
        print("=" * 100)

    def _print_row(self, filename: str, stmt_data: CoverageStats, branch_data: Optional[CoverageStats],
                   project_root: str) -> None:
        rel_name = os.path.relpath(filename, project_root)

        stmt_pct = stmt_data['pct']
        stmt_miss = sorted(list(stmt_data['missing']))

        branch_pct = 0
        branch_miss = []
        has_branches = False

        if branch_data:
            possible = branch_data['possible']
            if possible:
                has_branches = True
                branch_pct = branch_data['pct']
                branch_miss = sorted(list(branch_data['missing']))

        missing_items = []

        if stmt_miss:
            if len(stmt_miss) > 5:
                missing_items.append(f"L{stmt_miss[0]}..L{stmt_miss[-1]}")
            else:
                missing_items.append(f"Lines: {','.join(map(str, stmt_miss))}")

        if branch_miss:
            arcs_str = [f"{start}->{end}" for start, end in branch_miss]
            if len(arcs_str) > 3:
                missing_items.append(f"Branches: {len(arcs_str)} missed")
            else:
                missing_items.append(f"Br: {', '.join(arcs_str)}")

        miss_str = "; ".join(missing_items)
        if not miss_str:
            miss_str = ""

        if not has_branches:
            branch_str = "N/A"
        else:
            branch_str = f"{branch_pct:>3.0f}%"

        print(f"{rel_name:<25} | {stmt_pct:>6.0f}% | {branch_str:>11} | {miss_str}")


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


class XmlReporter(BaseReporter):
    """
    Generates a Cobertura-compatible XML coverage report.
    Useful for integration with CI/CD tools like Jenkins or Codecov.
    """

    def __init__(self, output_file: str = "coverage.xml") -> None:
        self.output_file = output_file

    def generate(self, results: AnalysisResults, project_root: str) -> None:
        print(f"Generating XML report to {self.output_file}...")

        # calculate global stats
        total_lines_valid = 0
        total_lines_covered = 0
        total_branches_valid = 0
        total_branches_covered = 0

        for file_res in results.values():
            stmt = file_res.get('Statement')
            if stmt:
                total_lines_valid += len(stmt['possible'])
                total_lines_covered += len(stmt['executed'])

            branch = file_res.get('Branch')
            if branch:
                total_branches_valid += len(branch['possible'])
                total_branches_covered += len(branch['executed'])

        line_rate = (total_lines_covered / total_lines_valid) if total_lines_valid > 0 else 1.0
        branch_rate = (total_branches_covered / total_branches_valid) if total_branches_valid > 0 else 1.0

        root = ET.Element("coverage")
        root.set("line-rate", str(line_rate))
        root.set("branch-rate", str(branch_rate))
        root.set("lines-covered", str(total_lines_covered))
        root.set("lines-valid", str(total_lines_valid))
        root.set("branches-covered", str(total_branches_covered))
        root.set("branches-valid", str(total_branches_valid))
        root.set("complexity", "0")
        root.set("version", "1.0")
        root.set("timestamp", str(int(time.time())))

        sources = ET.SubElement(root, "sources")
        source = ET.SubElement(sources, "source")
        source.text = project_root

        packages = ET.SubElement(root, "packages")
        package = ET.SubElement(packages, "package")
        package.set("name", ".")
        package.set("line-rate", str(line_rate))
        package.set("branch-rate", str(branch_rate))
        package.set("complexity", "0")

        classes = ET.SubElement(package, "classes")

        for filename in sorted(results.keys()):
            rel_name = os.path.relpath(filename, project_root)
            file_data = results[filename]
            stmt = file_data.get('Statement')
            if not stmt:
                continue

            file_line_rate = stmt['pct'] / 100.0

            # xml class element
            cls = ET.SubElement(classes, "class")
            cls.set("name", rel_name.replace(".py", ""))
            cls.set("filename", rel_name)
            cls.set("line-rate", str(file_line_rate))

            # branches for this file
            branch = file_data.get('Branch')
            file_branch_rate = (branch['pct'] / 100.0) if branch else 0.0
            cls.set("branch-rate", str(file_branch_rate))
            cls.set("complexity", "0")

            # lines
            lines_elem = ET.SubElement(cls, "lines")

            # combine line hits and branches for line-level details
            all_lines = stmt['possible']
            executed = stmt['executed']

            # map branches to lines
            branch_map = collections.defaultdict(list)
            if branch:
                for start, end in branch['possible']:
                    branch_map[start].append(end)

                # executed branches
                executed_branches = set(branch['executed'])

            for lineno in sorted(all_lines):
                line_elem = ET.SubElement(lines_elem, "line")
                line_elem.set("number", str(lineno))
                hits = 1 if lineno in executed else 0
                line_elem.set("hits", str(hits))

                # branch info
                if lineno in branch_map:
                    targets = branch_map[lineno]
                    line_elem.set("branch", "true")

                    # calculate coverage for this specific line's branches
                    covered_count = 0
                    for t in targets:
                        if (lineno, t) in executed_branches:
                            covered_count += 1

                    coverage_percent = int((covered_count / len(targets)) * 100)
                    line_elem.set("condition-coverage", f"{coverage_percent}% ({covered_count}/{len(targets)})")
                else:
                    line_elem.set("branch", "false")

        tree = ET.ElementTree(root)
        with open(self.output_file, "wb") as f:
            tree.write(f, encoding="utf-8", xml_declaration=True)


class JsonReporter(BaseReporter):
    """
    Generates a JSON report for programmatic consumption.
    """

    def __init__(self, output_file: str = "coverage.json") -> None:
        self.output_file = output_file

    def generate(self, results: AnalysisResults, project_root: str) -> None:
        print(f"Generating JSON report to {self.output_file}...")

        # transform sets to lists for json serialization
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