import sys
from src.metrics import StatementCoverage
from .base import TestMetricsBase


class TestStatementCoverage(TestMetricsBase):
    def setUp(self):
        self.metric = StatementCoverage()

    def test_simple_assignments(self):
        code = "x = 1\ny = 2\nz = x + y"
        tree = self.parse_code(code)
        lines = self.metric.get_possible_elements(tree, set())
        self.assertEqual(lines, {1, 2, 3})

    def test_ignore_docstrings_and_constants(self):
        code = """
'docstring'
x = 1
123 # constant number
y = 2
"""
        tree = self.parse_code(code)
        lines = self.metric.get_possible_elements(tree, set())
        self.assertEqual(lines, {3, 5})

    def test_pragma_ignore(self):
        code = """
x = 1
y = 2
z = 3
"""
        tree = self.parse_code(code)
        lines = self.metric.get_possible_elements(tree, {3})
        self.assertEqual(lines, {2, 4})

    def test_stats_calculation(self):
        possible = {1, 2, 3, 4}
        executed = {1, 2}
        stats = self.metric.calculate_stats(possible, executed)
        self.assertEqual(stats['pct'], 50.0)
        self.assertEqual(stats['missing'], {3, 4})
        self.assertEqual(stats['executed'], {1, 2})

    def test_empty_stats(self):
        stats = self.metric.calculate_stats(set(), set())
        self.assertEqual(stats['pct'], 100.0)

    def test_async_functions(self):
        code = """
async def fetch():
    x = 1
    await foo()
"""
        tree = self.parse_code(code)
        lines = self.metric.get_possible_elements(tree, set())
        self.assertTrue({2, 3, 4}.issubset(lines))

    def test_decorators(self):
        code = """
@decorator
def func():
    pass
"""
        tree = self.parse_code(code)
        lines = self.metric.get_possible_elements(tree, set())
        # Function def is line 3. Body is line 4.
        self.assertIn(3, lines)
        self.assertIn(4, lines)

    def test_walrus_operator(self):
        if sys.version_info < (3, 8): return
        code = """
if (x := 1) > 0:
    y = 2
"""
        tree = self.parse_code(code)
        lines = self.metric.get_possible_elements(tree, set())
        self.assertEqual(lines, {2, 3})

    def test_annotated_assignments(self):
        code = """
x: int = 1
y: str
"""
        tree = self.parse_code(code)
        lines = self.metric.get_possible_elements(tree, set())
        self.assertIn(2, lines)
