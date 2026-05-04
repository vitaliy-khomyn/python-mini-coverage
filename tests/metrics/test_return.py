from .base import TestMetricsBase
from src.metrics.return_coverage import ReturnCoverage


class TestReturnCoverage(TestMetricsBase):
    def setUp(self):
        self.metric = ReturnCoverage()

    def get_returns(self, code, ignored=None):
        tree = self.parse_code(code)
        return self.metric.get_possible_elements(tree, ignored or set())

    def test_simple_return(self):
        code = """
def f():
    return 1
"""
        self.assertEqual(self.get_returns(code), {3})

    def test_multiple_returns(self):
        code = """
def f(x):
    if x:
        return 1
    return 0
"""
        self.assertEqual(self.get_returns(code), {4, 5})

    def test_no_returns(self):
        code = """
def f():
    pass
"""
        self.assertEqual(self.get_returns(code), set())
