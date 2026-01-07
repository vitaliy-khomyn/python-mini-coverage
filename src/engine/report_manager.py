from typing import List
from ..reporters.base import AnalysisResults
from ..reporters.console import ConsoleReporter
from ..reporters.html import HtmlReporter
from ..reporters.xml import XmlReporter
from ..reporters.json import JsonReporter


class ReportManager:
    def __init__(self, reporters: List[str]):
        self.reporters = []
        for r in reporters:
            if r == 'console':
                self.reporters.append(ConsoleReporter())
            elif r == 'html':
                self.reporters.append(HtmlReporter(output_dir="htmlcov"))
            elif r == 'xml':
                self.reporters.append(XmlReporter(output_file="coverage.xml"))
            elif r == 'json':
                self.reporters.append(JsonReporter(output_file="coverage.json"))

    def generate(self, results: AnalysisResults, project_root: str) -> None:
        for reporter in self.reporters:
            reporter.generate(results, project_root)
