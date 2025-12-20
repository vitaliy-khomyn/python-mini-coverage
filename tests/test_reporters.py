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
        # Create dummy file1.py so HTML reporter can read it
        self.create_file("file1.py", "line1\nline2\nline3\nline4\nline5")

    def test_console_reporter_runs(self):
        reporter = ConsoleReporter()
        # Just ensure it doesn't crash and prints something
        with self.capture_stdout() as output:
            reporter.print_report(self.results, self.project_root)
            text = output.getvalue()

        self.assertIn("file1.py", text)
        self.assertIn("50%", text)
        self.assertIn("L1..L2", text)  # Formatting check
        self.assertIn("3->5", text)  # Branch check

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
        # Line 1 is missing -> 'miss' class
        self.assertIn('class="line miss"', content)
        # Line 3 is hit -> 'hit' class (but might be partial due to branch)
        # Our data says line 3 is executed, but branch (3,5) is missing.
        # So class should be 'partial'
        self.assertIn('class="line partial"', content)
        self.assertIn('Missed branch to: 5', content)