from .base import TestMetricsBase
from src.metrics.call_site import CallSiteCoverage


class TestCallSiteCoverage(TestMetricsBase):
    def setUp(self):
        self.metric = CallSiteCoverage()

    def get_calls(self, code, ignored=None):
        tree = self.parse_code(code)
        return self.metric.get_possible_elements(tree, ignored or set())

    def test_simple_call(self):
        code = """
def my_func():
    pass
my_func()
"""
        calls = self.get_calls(code)
        self.assertEqual(calls, {("my_func", 4)})

    def test_method_call(self):
        code = """
obj.do_something()
"""
        calls = self.get_calls(code)
        self.assertEqual(calls, {("do_something", 2)})

    def test_calculate_stats(self):
        possible = {("func_a", 2), ("func_b", 4)}
        executed_lines = {2, 10}
        stats = self.metric.calculate_stats(possible, executed_lines)

        self.assertEqual(stats['possible'], possible)
        self.assertEqual(stats['executed'], {("func_a", 2)})
        self.assertEqual(stats['missing'], {("func_b", 4)})
        self.assertEqual(stats['pct'], 50.0)
        self.assertEqual(stats['ratio'], "1/2")
