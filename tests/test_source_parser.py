import unittest  # noqa: F401
import ast
import os
import textwrap
import types
from src.source_parser import SourceParser
from tests.test_utils import BaseTestCase


class TestSourceParser(BaseTestCase):

    def setUp(self):
        super().setUp()
        self.parser = SourceParser()

    def test_parse_valid_python(self):
        path = self.create_file("valid.py", "x = 1\ny = 2")
        tree, ignored = self.parser.parse_source(path)
        self.assertIsInstance(tree, ast.Module)
        self.assertEqual(len(ignored), 0)

    def test_parse_syntax_error(self):
        path = self.create_file("invalid.py", "def broken(")
        tree, ignored = self.parser.parse_source(path)
        self.assertIsNone(tree)

    def test_pragma_detection_simple(self):
        code = textwrap.dedent("""\
        x = 1
        if x:
            pass # pragma: no cover
        """)
        path = self.create_file("pragma.py", code)
        _, ignored = self.parser.parse_source(path)
        self.assertIn(3, ignored)

    def test_exclude_patterns_regex(self):
        code = textwrap.dedent("""\
        x = 1
        def __repr__(self):
            return 'repr'
        if __name__ == "__main__":
            run()
        """)
        path = self.create_file("exclude.py", code)

        patterns = [
            r"def __repr__",
            r"if __name__ == .__main__.:"
        ]

        _, ignored = self.parser.parse_source(path, exclude_patterns=patterns)

        self.assertIn(2, ignored)  # def __repr__ matches
        self.assertIn(4, ignored)  # if main matches
        self.assertNotIn(1, ignored)

    def test_compile_source_success(self):
        path = self.create_file("ok.py", "print('hello')")
        co = self.parser.compile_source(path)
        self.assertIsInstance(co, types.CodeType)
        self.assertEqual(co.co_filename, path)

    def test_compile_source_error(self):
        path = self.create_file("err.py", "if x:")
        co = self.parser.compile_source(path)
        self.assertIsNone(co)

    def test_encoding_latin1(self):
        # Create a file with latin-1 encoded char
        path = os.path.join(self.test_dir, "latin.py")
        with open(path, 'wb') as f:
            f.write(b"# -*- coding: latin-1 -*-\nx = '\xe9'")  # é

        # parser assumes utf-8 by default but compile might handle magic comment
        # parse_source opens with utf-8, so it might fail or replace.
        # compile_source uses default open, which respects coding header if passed to compile?
        # actually implementation uses open(encoding='utf-8') which will fail for strict latin-1 chars not in utf-8.
        # this tests graceful failure.
        tree, _ = self.parser.parse_source(path)
        # should return None due to UnicodeDecodeError
        self.assertIsNone(tree)
