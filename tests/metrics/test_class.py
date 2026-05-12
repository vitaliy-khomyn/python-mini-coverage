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

    def test_dataclass_ignored(self):
        # Currently, ClassCoverage requires an explicit __init__ in the AST body.
        # @dataclass auto-generates __init__ at runtime, so it is bypassed by the static analyzer.
        code = """
from dataclasses import dataclass

@dataclass
class Point:
    x: int
    y: int
"""
        classes = self.get_classes(code)
        self.assertEqual(classes, set())

    def test_class_with_new_only(self):
        # Classes that only define __new__ and not __init__ are currently not tracked.
        code = """
class Singleton:
    def __new__(cls):
        return super().__new__(cls)
"""
        classes = self.get_classes(code)
        self.assertEqual(classes, set())

    def test_inherited_init(self):
        # Classes that inherit __init__ do not have it in their AST body.
        # Therefore, only the Parent class is tracked.
        code = """
class Parent:
    def __init__(self):
        self.a = 1

class Child(Parent):
    def method(self):
        pass
"""
        classes = self.get_classes(code)
        self.assertEqual(classes, {("Parent", 2, 4)})

    def test_dynamic_type_creation_ignored(self):
        # type() dynamic classes do not have an ast.ClassDef, so static analysis skips them.
        code = "DynamicClass = type('DynamicClass', (object,), {'__init__': lambda self: None})"
        classes = self.get_classes(code)
        self.assertEqual(classes, set())

    def test_inner_class(self):
        code = """
def factory():
    class Inner:
        def __init__(self):
            self.x = 1
    return Inner
"""
        classes = self.get_classes(code)
        self.assertEqual(classes, {("Inner", 3, 5)})

    def test_class_with_init_not_first(self):
        code = """
class MyClass:
    def some_method(self):
        pass

    def __init__(self):
        self.a = 1
"""
        classes = self.get_classes(code)
        self.assertEqual(classes, {("MyClass", 2, 7)})
