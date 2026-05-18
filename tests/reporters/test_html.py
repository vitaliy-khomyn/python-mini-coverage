import unittest  # noqa: F401
import os
from src.reporters import HtmlReporter
from tests.test_utils import BaseTestCase


class TestHtmlReporter(BaseTestCase):

    def setUp(self):
        super().setUp()

        self.filename = "main.py"
        self.filepath = self.create_file(self.filename, "x=1\ny=2")
        self.project_root = self.test_dir

        self.results = {
            self.filepath: {
                'Statement': {
                    'pct': 50.0,
                    'missing': {2},
                    'executed': {1},
                    'possible': {1, 2}
                },
                'Branch': {
                    'pct': 0.0,
                    'missing': {(1, 2)},
                    'executed': set(),
                    'possible': {(1, 2)}
                }
            }
        }

    def test_html_reporter_structure(self):
        out_dir = os.path.join(self.test_dir, "htmlcov")
        reporter = HtmlReporter(output_dir=out_dir)

        with self.assertLogs(reporter.logger, level='INFO'):
            reporter.generate(self.results, self.project_root)

        self.assertTrue(os.path.exists(os.path.join(out_dir, "index.html")))

        rel_name = os.path.relpath(self.filepath, self.project_root)
        sanitized_name = reporter._sanitize_filename(rel_name)
        expected_html_file = f"{sanitized_name}.html"

        self.assertTrue(os.path.exists(os.path.join(out_dir, expected_html_file)))

    def test_html_missing_source_file(self):
        os.remove(self.filepath)
        out_dir = os.path.join(self.test_dir, "htmlcov_err")
        reporter = HtmlReporter(output_dir=out_dir)

        with self.assertLogs(reporter.logger, level='INFO'):
            reporter.generate(self.results, self.project_root)

        rel_name = os.path.relpath(self.filepath, self.project_root)
        sanitized_name = reporter._sanitize_filename(rel_name)
        expected_html_file = f"{sanitized_name}.html"

        with open(os.path.join(out_dir, expected_html_file), "r", encoding="utf-8") as f:
            content = f.read()
            self.assertIn("Error reading source file.", content)

    def test_html_multiple_annotations(self):
        out_dir = os.path.join(self.test_dir, "htmlcov_multi")
        reporter = HtmlReporter(output_dir=out_dir)

        res = {
            self.filepath: {
                'Statement': {'pct': 50.0, 'missing': {2}, 'executed': {1}, 'possible': {1, 2}},
                'Branch': {'pct': 0.0, 'missing': {(2, 3)}, 'executed': set(), 'possible': {(2, 3)}},
                'MMC/DC': {'pct': 50.0, 'missing_outcomes': {2: {'ratio': '1/2', 'total': 2, 'covered': 1, 'conditions': 1, 'missing': [{'message': 'Condition 1 missed', 'terminal': True}]}}},
                'Return': {'pct': 0.0, 'missing': {2}, 'executed': set(), 'possible': {2}}
            }
        }

        with self.assertLogs(reporter.logger, level='INFO'):
            reporter.generate(res, self.project_root)

        rel_name = os.path.relpath(self.filepath, self.project_root)
        sanitized_name = reporter._sanitize_filename(rel_name)
        expected_html_file = f"{sanitized_name}.html"

        with open(os.path.join(out_dir, expected_html_file), "r", encoding="utf-8") as f:
            content = f.read()
            self.assertIn("3 Missing Details", content)
            self.assertIn("Missed branch to: <a href=\"#L3\">3</a>", content)
            self.assertIn("MMC/DC Coverage: 1/2", content)
            self.assertIn("Missed return statement", content)
