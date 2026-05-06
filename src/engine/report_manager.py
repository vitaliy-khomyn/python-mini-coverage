from ..reporters.base import AnalysisResults
from ..reporters.console import ConsoleReporter
from ..reporters.html import HtmlReporter
from ..reporters.xml import XmlReporter
from ..reporters.json import JsonReporter
from .config import ReporterType


class ReportManager:
    def __init__(self, config):
        self.config = config
        self.reporters = []
        for r in config.reporters:
            if r == ReporterType.CONSOLE:
                self.reporters.append(ConsoleReporter(config))
            elif r == ReporterType.HTML:
                self.reporters.append(HtmlReporter(config=config, output_dir="htmlcov"))
            elif r == ReporterType.XML:
                self.reporters.append(XmlReporter(config=config, output_file="coverage.xml"))
            elif r == ReporterType.JSON:
                self.reporters.append(JsonReporter(config=config, output_file="coverage.json"))

    def generate(self, results: AnalysisResults, project_root: str) -> None:
        for reporter in self.reporters:
            reporter.generate(results, project_root)
