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
        METRICS_CONFIG = [
            {'key': 'stmt', 'name': 'Statement', 'display': 'Statements'},
            {'key': 'branch', 'name': 'Branch', 'display': 'Branches'},
            {'key': 'cond', 'name': 'Condition', 'display': 'Conditions'},
            {'key': 'func', 'name': 'Function', 'display': 'Functions'},
            {'key': 'loop', 'name': 'Loop', 'display': 'Loops'},
        ]
        totals = {m['key']: {'possible': 0, 'missing': 0} for m in METRICS_CONFIG}

        rows = ""
        for filename in sorted(results.keys()):
            # Collect data for all metrics for the current file
            file_metrics_list = []
            has_statement_data = False
            for cfg in METRICS_CONFIG:
                metric_data = results[filename].get(cfg['name'], {})
                metric_data.setdefault('pct', 0)
                metric_data.setdefault('ratio', "0/0")
                file_metrics_list.append(metric_data)

                if cfg['name'] == 'Statement' and metric_data.get('possible'):
                    has_statement_data = True

                # Aggregate totals
                key = cfg['key']
                if cfg['name'] == 'Condition':
                    missing_outcomes = metric_data.get('missing_outcomes', {})
                    if missing_outcomes:
                        for line_stats in missing_outcomes.values():
                            totals[key]['possible'] += line_stats.get('total', 0)
                            totals[key]['missing'] += len(line_stats.get('missing', []))
                    else:
                        totals[key]['possible'] += len(metric_data.get('possible', []))
                        totals[key]['missing'] += len(metric_data.get('missing', []))
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
        def calc_pct(poss, miss):
            if poss == 0: return 100.0
            return ((poss - miss) / poss) * 100.0

        def calc_ratio(poss, miss):
            return f"{poss - miss}/{poss}"

        total_stats = []
        for cfg in METRICS_CONFIG:
            key = cfg['key']
            poss, miss = totals[key]['possible'], totals[key]['missing']
            total_stats.append({
                'display': cfg['display'],
                'pct': calc_pct(poss, miss),
                'ratio': calc_ratio(poss, miss)
            })

        html_content = templates.render_index([m['display'] for m in METRICS_CONFIG], total_stats, rows)

        with open(os.path.join(self.output_dir, "index.html"), "w", encoding="utf-8") as f:
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

        cond_data = data.get('Condition')
        missing_conditions = cond_data.get('missing_outcomes', {}) if cond_data else {}

        func_data = data.get('Function')
        missing_functions = {}
        if func_data and func_data.get('missing'):
            # Recreate the map from the raw missing elements tuple: (name, def_line, first_exec_line)
            missing_functions = {func[1]: f"Function '{func[0]}' was not called" for func in func_data['missing']}

        loop_data = data.get('Loop')
        missing_loops = collections.defaultdict(list)
        if loop_data and loop_data.get('missing'):
            for start, end in loop_data['missing']:
                missing_loops[start].append(end)

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
            details = None

            if lineno in executed_lines:
                css_class = "hit"
            elif lineno in missing_lines:
                css_class = "miss"

            if lineno in missing_functions:
                css_class = "miss"
                annotation += f"<span class='annotate'>{html.escape(missing_functions[lineno])}</span>"

            if lineno in missing_loops:
                if css_class == "hit":
                    css_class = "partial"
                annotation += "<span class='annotate'>Missed loop path(s)</span>"

            if lineno in missing_branches:
                targets = missing_branches[lineno]
                if css_class == "hit":
                    css_class = "partial"

                targets_str = ", ".join(map(str, targets))
                annotation = f"<span class='annotate'>Missed branch to: {targets_str}</span>"

            if lineno in missing_conditions:
                cond_info = missing_conditions[lineno]
                if isinstance(cond_info, dict) and 'ratio' in cond_info:
                    if cond_info['missing']:
                        annotation += f"<span class='annotate condition'>Coverage: {cond_info['ratio']}</span>"
                        if css_class == "hit":
                            css_class = "cond-partial"
                        rows = ""
                        for item in cond_info['missing']:
                            # item is dict {'vector': str, 'terminal': bool}
                            vec = item.get('vector', str(item))
                            rows += f"<tr><td>{html.escape(vec)}</td></tr>"
                        details = f"<strong>Missing Cases:</strong><table class='condition-table'><thead><tr><th>Conditions</th></tr></thead><tbody>{rows}</tbody></table>"
                else:
                    # Fallback for legacy format
                    if css_class == "hit":
                        css_class = "cond-partial"
                    conds = cond_info
                    cond_str = ", ".join(sorted(set(conds)))
                    annotation += f"<span class='annotate condition'>Condition Missing: {cond_str}</span>"

            line_content = html.escape(line.rstrip())
            code_html += templates.render_code_line(lineno, line_content, css_class, annotation, details)

        html_content = templates.render_file(html.escape(rel_name), code_html)

        with open(os.path.join(self.output_dir, out_name), "w", encoding="utf-8") as f:
            f.write(html_content)

    def _sanitize_filename(self, path: str) -> str:
        return path.replace(os.sep, "_").replace(".", "_")
