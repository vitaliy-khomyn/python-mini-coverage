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

        reporter_factories = {
            ReporterType.CONSOLE: lambda cfg: ConsoleReporter(cfg),
            ReporterType.HTML: lambda cfg: HtmlReporter(config=cfg, output_dir="htmlcov"),
            ReporterType.XML: lambda cfg: XmlReporter(config=cfg, output_file="coverage.xml"),
            ReporterType.JSON: lambda cfg: JsonReporter(config=cfg, output_file="coverage.json")
        }

        for r in config.reporters:
            if r in reporter_factories:
                self.reporters.append(reporter_factories[r](config))

    def generate(self, results: AnalysisResults, project_root: str) -> None:
        for reporter in self.reporters:
            reporter.generate(results, project_root)
