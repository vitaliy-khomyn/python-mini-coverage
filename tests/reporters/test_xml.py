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
        XmlReporter("e.xml").generate(empty, self.test_dir)
        tree = ET.parse("e.xml")
        self.assertEqual(tree.getroot().attrib["lines-covered"], "0")
