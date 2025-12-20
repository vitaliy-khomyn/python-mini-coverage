import unittest
import os
from src.reporters import ConsoleReporter, HtmlReporter
from tests.test_utils import BaseTestCase


class TestReporters(BaseTestCase):

    def setUp(self):
        super().setUp()
        self.results = {
            'file1.py': {
                'Statement': {
                    'pct': 50.0,
                    'missing': {1, 2},
                    'executed': {3, 4},
                    'possible': {1, 2, 3, 4}
                },
                'Branch': {
                    'pct': 0.0,
                    'missing': {(3, 5)},
                    'possible': {(3, 5)}
                }
            }
        }
        self.project_root = self.test_dir
        self.create_file("file1.py", "line1\nline2\nline3\nline4\nline5")

    def test_console_reporter_runs(self):
        reporter = ConsoleReporter()
        with self.capture_stdout() as output:
            reporter.print_report(self.results, self.project_root)
            text = output.getvalue()

        self.assertIn("file1.py", text)
        self.assertIn("50%", text)
        # Check for uncompressed format since we only have 2 missing lines
        self.assertIn("Lines: 1,2", text)
        self.assertIn("Br: 3->5", text)

    def test_console_reporter_empty(self):
        reporter = ConsoleReporter()
        with self.capture_stdout() as output:
            reporter.print_report({}, self.project_root)
            text = output.getvalue()
        self.assertIn("File", text)

    def test_html_reporter_generation(self):
        out_dir = os.path.join(self.test_dir, "htmlcov")
        reporter = HtmlReporter(output_dir=out_dir)

        with self.capture_stdout():
            reporter.generate(self.results, self.project_root)

        self.assertTrue(os.path.exists(out_dir))
        self.assertTrue(os.path.exists(os.path.join(out_dir, "index.html")))
        self.assertTrue(os.path.exists(os.path.join(out_dir, "file1_py.html")))

    def test_html_content_index(self):
        out_dir = os.path.join(self.test_dir, "htmlcov")
        reporter = HtmlReporter(output_dir=out_dir)
        with self.capture_stdout():
            reporter.generate(self.results, self.project_root)

        with open(os.path.join(out_dir, "index.html")) as f:
            content = f.read()

        self.assertIn("file1.py", content)
        self.assertIn("50%", content)

    def test_html_content_file(self):
        out_dir = os.path.join(self.test_dir, "htmlcov")
        reporter = HtmlReporter(output_dir=out_dir)
        with self.capture_stdout():
            reporter.generate(self.results, self.project_root)

        with open(os.path.join(out_dir, "file1_py.html")) as f:
            content = f.read()

        self.assertIn('<span class="lineno">1</span>', content)
        self.assertIn('class="line miss"', content)
        self.assertIn('class="line partial"', content)
        self.assertIn('Missed branch to: 5', content)