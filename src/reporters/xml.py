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

            cls = ET.SubElement(classes, "class")
            cls.set("name", rel_name.replace(".py", ""))
            cls.set("filename", rel_name)
            cls.set("line-rate", str(file_line_rate))

            branch = file_data.get('Branch')
            file_branch_rate = (branch['pct'] / 100.0) if branch else 0.0
            cls.set("branch-rate", str(file_branch_rate))
            cls.set("complexity", "0")

            lines_elem = ET.SubElement(cls, "lines")

            all_lines = stmt['possible']
            executed = stmt['executed']

            branch_map = collections.defaultdict(list)
            executed_branches = set()
            if branch:
                for start, end in branch['possible']:
                    branch_map[start].append(end)
                executed_branches = set(branch['executed'])

            for lineno in sorted(all_lines):
                line_elem = ET.SubElement(lines_elem, "line")
                line_elem.set("number", str(lineno))
                hits = 1 if lineno in executed else 0
                line_elem.set("hits", str(hits))

                if lineno in branch_map:
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
