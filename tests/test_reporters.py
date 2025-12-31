import unittest
import os
import json
import xml.etree.ElementTree as ET
from src.reporters import ConsoleReporter, HtmlReporter, XmlReporter, JsonReporter
from tests.test_utils import BaseTestCase


class TestReporters(BaseTestCase):

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

    def test_xml_reporter_structure(self):
        out_file = os.path.join(self.test_dir, "coverage.xml")
        reporter = XmlReporter(output_file=out_file)

        with self.capture_stdout():
            reporter.generate(self.results, self.project_root)

        tree = ET.parse(out_file)
        root = tree.getroot()
        self.assertEqual(root.tag, "coverage")
        self.assertEqual(root.attrib["line-rate"], "0.5")

        source = root.find(".//sources/source")
        self.assertEqual(source.text, self.project_root)

        rel_name = os.path.relpath(self.filepath, self.project_root)
        # XML reporter uses filename attribute to match
        cls = root.find(f".//class[@filename='{rel_name}']")
        self.assertIsNotNone(cls)
        self.assertEqual(cls.attrib["line-rate"], "0.5")

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

    def test_empty_results_handling(self):
        empty = {}
        # Console
        with self.capture_stdout() as o:
            ConsoleReporter().generate(empty, self.test_dir)

        # XML
        XmlReporter("e.xml").generate(empty, self.test_dir)
        tree = ET.parse("e.xml")
        self.assertEqual(tree.getroot().attrib["lines-covered"], "0")

        # JSON
        JsonReporter("e.json").generate(empty, self.test_dir)
        with open("e.json") as f:
            self.assertEqual(json.load(f)["files"], {})
