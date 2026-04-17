from .base import TestMetricsBase
from src.metrics.class_coverage import ClassCoverage


class TestClassCoverage(TestMetricsBase):
    def setUp(self):
        self.metric = ClassCoverage()

    def get_classes(self, code, ignored=None):
        tree = self.parse_code(code)
        return self.metric.get_possible_elements(tree, ignored or set())

    def test_simple_class(self):
        code = """
class MyClass:
    def __init__(self):
        self.a = 1
"""
        classes = self.get_classes(code)
        # (name, def_line, init_first_line)
        self.assertEqual(classes, {("MyClass", 2, 4)})

    def test_class_without_init(self):
        code = """
class NoInit:
    def some_method(self):
        pass
"""
        classes = self.get_classes(code)
        self.assertEqual(classes, set())

    def test_class_with_docstring_in_init(self):
        code = """
class MyClass:
    def __init__(self):
        "docstring"
        self.a = 1
"""
        classes = self.get_classes(code)
        self.assertEqual(classes, {("MyClass", 2, 5)})

    def test_multiple_classes(self):
        code = """
class A:
    def __init__(self):
        pass

class B:
    def __init__(self):
        self.b = 1
"""
        classes = self.get_classes(code)
        expected = {
            ("A", 2, 4),
            ("B", 6, 8)
        }
        self.assertEqual(classes, expected)

    def test_calculate_stats(self):
        possible = {("A", 2, 4), ("B", 6, 8)}
        executed_lines = {4, 10, 12}  # Class A is instantiated, B is not
        stats = self.metric.calculate_stats(possible, executed_lines)

        self.assertEqual(stats['possible'], possible)
        self.assertEqual(stats['executed'], {("A", 2, 4)})
        self.assertEqual(stats['missing'], {("B", 6, 8)})
        self.assertEqual(stats['pct'], 50.0)
        self.assertEqual(stats['ratio'], "1/2")