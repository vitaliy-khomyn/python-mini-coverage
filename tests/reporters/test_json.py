import unittest  # noqa: F401
import os
import json
from src.reporters import JsonReporter
from tests.test_utils import BaseTestCase


class TestJsonReporter(BaseTestCase):

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

    def test_json_reporter_structure(self):
        out_file = os.path.join(self.test_dir, "coverage.json")
        reporter = JsonReporter(output_file=out_file)

        with self.capture_stdout():
            reporter.generate(self.results, self.project_root)

        with open(out_file) as f:
            data = json.load(f)

        self.assertIn("meta", data)
        self.assertEqual(data["meta"]["project_root"], self.project_root)

        rel_name = os.path.relpath(self.filepath, self.project_root)
        self.assertIn(rel_name, data["files"])
        self.assertEqual(data["files"][rel_name]["Statement"]["missing"], [2])

    def test_empty_results(self):
        empty = {}
        JsonReporter("e.json").generate(empty, self.test_dir)
        with open("e.json") as f:
            self.assertEqual(json.load(f)["files"], {})
