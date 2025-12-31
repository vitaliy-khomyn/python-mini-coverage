import unittest  # noqa: F401
from src.reporters import ConsoleReporter
from tests.test_utils import BaseTestCase


class TestConsoleReporter(BaseTestCase):

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

    def test_console_reporter_basic(self):
        reporter = ConsoleReporter()
        with self.capture_stdout() as output:
            reporter.generate(self.results, self.project_root)
            text = output.getvalue()

        self.assertIn("main.py", text)
        self.assertIn("50%", text)
        self.assertIn("Lines: 2", text)

    def test_console_reporter_no_branches(self):
        f_path = self.create_file("f.py", "pass")
        res = {f_path: {'Statement': {'pct': 100, 'missing': set(), 'executed': {1}, 'possible': {1}}}}

        reporter = ConsoleReporter()
        with self.capture_stdout() as output:
            reporter.generate(res, self.project_root)
            text = output.getvalue()
        self.assertIn("N/A", text)

    def test_empty_results(self):
        empty = {}
        with self.capture_stdout() as _:
            ConsoleReporter().generate(empty, self.test_dir)
