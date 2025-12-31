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

        with self.capture_stdout():
            reporter.generate(self.results, self.project_root)

        self.assertTrue(os.path.exists(os.path.join(out_dir, "index.html")))

        rel_name = os.path.relpath(self.filepath, self.project_root)
        sanitized_name = reporter._sanitize_filename(rel_name)
        expected_html_file = f"{sanitized_name}.html"

        self.assertTrue(os.path.exists(os.path.join(out_dir, expected_html_file)))
