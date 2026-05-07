import sys
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

    def test_ignored_except(self):
        code = """
try:
    x = 1 / 0
except ZeroDivisionError:
    pass
"""
        self.assertEqual(self.get_excepts(code, ignored={4}), set())

    def test_calculate_stats(self):
        possible = {4, 6}
        executed = {4}
        stats = self.metric.calculate_stats(possible, executed)

        self.assertEqual(stats['possible'], possible)
        self.assertEqual(stats['executed'], {4})
        self.assertEqual(stats['missing'], {6})
        self.assertEqual(stats['pct'], 50.0)
        self.assertEqual(stats['ratio'], "1/2")

    def test_calculate_stats_empty(self):
        stats = self.metric.calculate_stats(set(), set())
        self.assertEqual(stats['pct'], 100.0)
        self.assertEqual(stats['ratio'], "0/0")

    def test_exception_path_accounting(self):
        code = """
def explode():
    raise ValueError()

try:
    if explode() and x:
        pass
except ValueError:
    pass
"""
        self.assertEqual(self.get_excepts(code), {8})

    def test_bare_except(self):
        code = """
try:
    pass
except:
    pass
"""
        self.assertEqual(self.get_excepts(code), {4})

    def test_exception_group(self):
        # Python 3.11+ except* syntax (Exception groups)
        if sys.version_info < (3, 11):
            return
        code = """
try:
    pass
except* ValueError:
    pass
"""
        self.assertEqual(self.get_excepts(code), {4})
