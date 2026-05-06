import unittest  # noqa: F401
import os
import xml.etree.ElementTree as ET
from src.reporters import XmlReporter
from tests.test_utils import BaseTestCase


class TestXmlReporter(BaseTestCase):

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

    def test_empty_results(self):
        empty = {}
        XmlReporter(output_file="e.xml").generate(empty, self.test_dir)
        tree = ET.parse("e.xml")
        self.assertEqual(tree.getroot().attrib["lines-covered"], "0")

    def test_xml_reporter_extended_metrics(self):
        res = {
            self.filepath: {
                'Statement': {'pct': 50.0, 'missing': {2}, 'executed': {1}, 'possible': {1, 2}},
                'Function': {'pct': 100.0, 'missing': set(), 'executed': {("my_func", 1, 2)}, 'possible': {("my_func", 1, 2)}},
                'Condition': {'pct': 50.0, 'missing_outcomes': {1: {'ratio': '1/2', 'total': 2, 'covered': 1, 'conditions': 1, 'missing': [{'message': 'Condition 1 missed', 'terminal': True}]}}},
                'MMC/DC': {'pct': 50.0, 'missing_outcomes': {1: {'ratio': '1/2', 'total': 2, 'covered': 1, 'conditions': 1, 'missing': [{'message': 'Condition 1 missed', 'terminal': True}]}}}
            }
        }
        out_file = os.path.join(self.test_dir, "coverage_ext.xml")
        reporter = XmlReporter(output_file=out_file)

        with self.capture_stdout():
            reporter.generate(res, self.project_root)

        tree = ET.parse(out_file)
        root = tree.getroot()
        self.assertEqual(root.attrib["function-rate"], "1.0")
        self.assertEqual(root.attrib["mmcdc-rate"], "0.5")
        self.assertEqual(root.attrib["condition-rate"], "0.5")

        methods = root.findall(".//class/methods/method")
        self.assertEqual(len(methods), 1)
        self.assertEqual(methods[0].attrib["name"], "my_func")

        lines = root.findall(".//class/lines/line")
        line1 = next(l for l in lines if l.attrib["number"] == "1")
        self.assertEqual(line1.attrib["branch"], "true")
        self.assertEqual(line1.attrib["condition-coverage"], "50% (1/2)")
