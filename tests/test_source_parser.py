import unittest
import ast
import os
import textwrap
from src.source_parser import SourceParser
from tests.test_utils import BaseTestCase


class TestSourceParser(BaseTestCase):

    def setUp(self):
        super().setUp()
        self.parser = SourceParser()

    def test_parse_valid_python(self):
        code = "x = 1\ny = 2"
        path = self.create_file("valid.py", code)
        tree, ignored = self.parser.parse_source(path)

        self.assertIsInstance(tree, ast.Module)
        self.assertEqual(len(ignored), 0)
        self.assertEqual(len(tree.body), 2)

    def test_parse_syntax_error(self):
        code = "def broken_func("
        path = self.create_file("invalid.py", code)
        tree, ignored = self.parser.parse_source(path)

        self.assertIsNone(tree)
        self.assertEqual(ignored, set())

    def test_parse_non_existent_file(self):
        tree, ignored = self.parser.parse_source("does_not_exist.py")
        self.assertIsNone(tree)
        self.assertEqual(ignored, set())

    def test_pragma_detection_simple(self):
        # Use dedent to fix indentation issues
        code = textwrap.dedent("""
        x = 1
        if x > 0:
            print("ignored") # pragma: no cover
        """)
        path = self.create_file("pragma.py", code)
        tree, ignored = self.parser.parse_source(path)

        # Line 3: print("ignored")...
        self.assertIn(3, ignored)
        self.assertEqual(len(ignored), 1)

    def test_pragma_detection_case_insensitive(self):
        code = textwrap.dedent("""
        x = 1 # PRAGMA: NO COVER
        y = 2 # pragma: no cover
        z = 3 # Pragma: No Cover
        """)
        path = self.create_file("pragma_case.py", code)
        _, ignored = self.parser.parse_source(path)
        # Lines 2, 3, 4
        self.assertEqual(ignored, {2, 3, 4})

    def test_pragma_detection_whitespace_variations(self):
        code = textwrap.dedent("""
        a = 1 #pragma:no cover
        b = 2 #    pragma:    no    cover   
        c = 3 # something else pragma: no cover
        """)
        path = self.create_file("pragma_spaces.py", code)
        _, ignored = self.parser.parse_source(path)
        self.assertEqual(ignored, {2, 3, 4})

    def test_encoding_utf8(self):
        code = "# -*- coding: utf-8 -*-\nx = '🚀'"
        path = self.create_file("utf8.py", code)
        tree, _ = self.parser.parse_source(path)
        self.assertIsNotNone(tree)

    def test_empty_file(self):
        path = self.create_file("empty.py", "")
        tree, ignored = self.parser.parse_source(path)
        self.assertIsInstance(tree, ast.Module)
        self.assertEqual(len(tree.body), 0)

    def test_pragma_no_code(self):
        code = "# just a comment # pragma: no cover"
        path = self.create_file("comment_pragma.py", code)
        _, ignored = self.parser.parse_source(path)
        self.assertIn(1, ignored)

    def test_binary_file_handling(self):
        filepath = os.path.join(self.test_dir, "binary.bin")
        with open(filepath, 'wb') as f:
            f.write(b'\x80\x00\x00')

        tree, ignored = self.parser.parse_source(filepath)
        self.assertIsNone(tree)

    def test_mixed_line_endings(self):
        content = "x = 1\r\ny = 2\n"
        path = self.create_file("crlf.py", content)
        tree, _ = self.parser.parse_source(path)
        self.assertIsNotNone(tree)
        self.assertEqual(len(tree.body), 2)