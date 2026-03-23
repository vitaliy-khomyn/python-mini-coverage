from .base import TestMetricsBase
from src.metrics import FunctionCoverage


class TestFunctionCoverage(TestMetricsBase):
    def setUp(self):
        self.metric = FunctionCoverage()

    def get_funcs(self, code, ignored=None):
        tree = self.parse_code(code)
        return self.metric.get_possible_elements(tree, ignored or set())

    def test_simple_function(self):
        code = """
def my_func():
    a = 1
"""
        funcs = self.get_funcs(code)
        # (name, def_line, first_exec_line)
        self.assertEqual(funcs, {("my_func", 2, 3)})

    def test_function_with_docstring(self):
        code = """
def my_func():
    "This is a docstring"
    a = 1
"""
        funcs = self.get_funcs(code)
        self.assertEqual(funcs, {("my_func", 2, 4)})

    def test_empty_function_pass(self):
        code = """
def empty_func():
    pass
"""
        funcs = self.get_funcs(code)
        self.assertEqual(funcs, {("empty_func", 2, 3)})

    def test_multiple_functions(self):
        code = """
def f1():
    x = 1

def f2():
    y = 2
"""
        funcs = self.get_funcs(code)
        expected = {
            ("f1", 2, 3),
            ("f2", 5, 6)
        }
        self.assertEqual(funcs, expected)

    def test_nested_function(self):
        code = """
def outer():
    def inner():
        a = 1
    b = 2
"""
        funcs = self.get_funcs(code)
        expected = {
            ("outer", 2, 3),
            ("inner", 3, 4)
        }
        self.assertEqual(funcs, expected)

    def test_async_function(self):
        code = """
async def my_async_func():
    await something()
"""
        funcs = self.get_funcs(code)
        self.assertEqual(funcs, {("my_async_func", 2, 3)})

    def test_calculate_stats(self):
        possible = {("f1", 2, 3), ("f2", 5, 6)}
        executed_lines = {3, 10, 12}  # f1 is hit, f2 is not
        stats = self.metric.calculate_stats(possible, executed_lines)

        self.assertEqual(stats['total'], 2)
        self.assertEqual(stats['covered'], 1)
        self.assertEqual(stats['missing'], 1)
        self.assertEqual(stats['percentage'], 50.0)
        self.assertEqual(stats['missing_elements'], {("f2", 5, 6)})

    def test_map_missing_elements(self):
        missing = {("my_func", 10, 11)}
        mapped = self.metric.map_missing_elements(missing)
        self.assertEqual(mapped, {10: "Function 'my_func' was not called"})
