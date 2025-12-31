import unittest
import ast


class TestMetricsBase(unittest.TestCase):
    def parse_code(self, code):
        return ast.parse(code)

    def compile_code(self, code):
        return compile(code, "<string>", "exec")
