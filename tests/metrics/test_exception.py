from .base import TestMetricsBase
from src.metrics.exception import ExceptionCoverage


class TestExceptionCoverage(TestMetricsBase):
    def setUp(self):
        self.metric = ExceptionCoverage()

    def get_excepts(self, code, ignored=None):
        tree = self.parse_code(code)
        return self.metric.get_possible_elements(tree, ignored or set())

    def test_simple_try_except(self):
        code = """
try:
    x = 1 / 0
except ZeroDivisionError:
    pass
"""
        excepts = self.get_excepts(code)
        self.assertEqual(excepts, {4})

    def test_multiple_excepts(self):
        code = """
try:
    pass
except ValueError:
    pass
except TypeError:
    pass
"""
        excepts = self.get_excepts(code)
        self.assertEqual(excepts, {4, 6})

    def test_no_excepts(self):
        code = "x = 1"
        self.assertEqual(self.get_excepts(code), set())
