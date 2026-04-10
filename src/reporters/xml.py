import os
import time
import collections
import xml.etree.ElementTree as ET
from .base import BaseReporter, AnalysisResults


class XmlReporter(BaseReporter):
    """
    Generates a Cobertura-compatible XML coverage report.
    Useful for integration with CI/CD tools like Jenkins or Codecov.
    """

    def __init__(self, output_file: str = "coverage.xml") -> None:
        self.output_file = output_file

    def generate(self, results: AnalysisResults, project_root: str) -> None:
        print(f"Generating XML report to {self.output_file}...")

        METRICS_CONFIG = [
            {'key': 'lines', 'name': 'Statement'},
            {'key': 'branches', 'name': 'Branch'},
            {'key': 'functions', 'name': 'Function'},
            {'key': 'loops', 'name': 'Loop'},  # Non-standard
        ]
        totals = {f"{cfg['key']}_valid": 0 for cfg in METRICS_CONFIG}
        totals.update({f"{cfg['key']}_covered": 0 for cfg in METRICS_CONFIG})

        for file_res in results.values():
            for cfg in METRICS_CONFIG:
                metric_data = file_res.get(cfg['name'])
                if metric_data:
                    totals[f"{cfg['key']}_valid"] += len(metric_data.get('possible', []))
                    totals[f"{cfg['key']}_covered"] += len(metric_data.get('executed', []))

        def calc_rate(key):
            valid = totals.get(f"{key}_valid", 0)
            covered = totals.get(f"{key}_covered", 0)
            return (covered / valid) if valid > 0 else 1.0

        line_rate = calc_rate('lines')
        branch_rate = calc_rate('branches')
        func_rate = calc_rate('functions')
        loop_rate = calc_rate('loops')

        root = ET.Element("coverage")
        root.set("line-rate", str(line_rate))
        root.set("branch-rate", str(branch_rate))
        # Non-standard, but useful for summary
        root.set("function-rate", str(func_rate))
        root.set("loop-rate", str(loop_rate))
        root.set("lines-covered", str(totals['lines_covered']))
        root.set("lines-valid", str(totals['lines_valid']))
        root.set("branches-covered", str(totals['branches_covered']))
        root.set("branches-valid", str(totals['branches_valid']))
        root.set("functions-covered", str(totals['functions_covered']))
        root.set("functions-valid", str(totals['functions_valid']))
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

            cls = ET.SubElement(classes, "class")
            cls.set("name", rel_name.replace(".py", ""))
            cls.set("filename", rel_name)
            cls.set("line-rate", str(file_line_rate))

            branch = file_data.get('Branch')
            file_branch_rate = (branch['pct'] / 100.0) if branch else 0.0
            cls.set("branch-rate", str(file_branch_rate))
            cls.set("complexity", "0")

            methods_elem = ET.SubElement(cls, "methods")
            func_data = file_data.get('Function')
            if func_data:
                all_funcs = func_data.get('possible', set())
                hit_funcs = func_data.get('executed', set())

                for func_tuple in sorted(list(all_funcs), key=lambda f: f[1]):
                    func_name, def_line, _ = func_tuple

                    method_elem = ET.SubElement(methods_elem, "method")
                    method_elem.set("name", func_name)
                    method_elem.set("signature", "()")
                    is_hit = func_tuple in hit_funcs
                    method_elem.set("line-rate", "1.0" if is_hit else "0.0")
                    method_elem.set("branch-rate", "0.0")  # Not measured per-function

                    method_lines_elem = ET.SubElement(method_elem, "lines")
                    line_elem = ET.SubElement(method_lines_elem, "line")
                    line_elem.set("number", str(def_line))
                    line_elem.set("hits", "1" if is_hit else "0")

            lines_elem = ET.SubElement(cls, "lines")

            all_lines = stmt['possible']
            executed = stmt['executed']

            branch_map = collections.defaultdict(list)
            executed_branches = set()
            if branch:
                for start, end in branch['possible']:
                    branch_map[start].append(end)
                executed_branches = set(branch['executed'])

            cond = file_data.get('Condition')
            cond_outcomes = cond.get('missing_outcomes', {}) if cond else {}

            for lineno in sorted(all_lines):
                line_elem = ET.SubElement(lines_elem, "line")
                line_elem.set("number", str(lineno))
                hits = 1 if lineno in executed else 0
                line_elem.set("hits", str(hits))

                if lineno in cond_outcomes:
                    # Use Condition Coverage data if available (more granular)
                    c_stat = cond_outcomes[lineno]
                    covered = c_stat.get('covered', 0)
                    total = c_stat.get('total', 0)
                    pct = int((covered / total) * 100) if total > 0 else 100
                    line_elem.set("condition-coverage", f"{pct}% ({covered}/{total})")
                    line_elem.set("branch", "true")
                elif lineno in branch_map:
                    targets = branch_map[lineno]
                    line_elem.set("branch", "true")

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
