import ast
from src.metrics import BranchCoverage
from .base import TestMetricsBase


class TestBranchCoverage(TestMetricsBase):
    def setUp(self):
        self.metric = BranchCoverage()

    def get_arcs(self, code, ignored=None):
        ignored = ignored or set()
        tree = self.parse_code(code)
        return self.metric.get_possible_elements(tree, ignored)

    def test_simple_if(self):
        code = """
if x > 0:
    y = 1
z = 2
"""
        arcs = self.get_arcs(code)
        self.assertEqual(arcs, {(2, 3), (2, 4)})

    def test_if_else(self):
        code = """
if x:
    y = 1
else:
    y = 2
z = 3
"""
        arcs = self.get_arcs(code)
        self.assertEqual(arcs, {(2, 3), (2, 5)})

    def test_if_elif_else(self):
        code = """
if x:
    a = 1
elif y:
    a = 2
else:
    a = 3
"""
        arcs = self.get_arcs(code)
        self.assertEqual(arcs, {(2, 3), (2, 4), (4, 5), (4, 7)})

    def test_nested_if(self):
        code = """
if x:
    if y:
        a = 1
    b = 2
c = 3
"""
        arcs = self.get_arcs(code)
        self.assertEqual(arcs, {(2, 3), (2, 6), (3, 4), (3, 5)})

    def test_while_loop(self):
        code = """
while x > 0:
    x -= 1
y = 2
"""
        arcs = self.get_arcs(code)
        self.assertEqual(arcs, {(2, 3), (2, 4)})

    def test_for_loop(self):
        code = """
for i in range(3):
    print(i)
print("done")
"""
        arcs = self.get_arcs(code)
        self.assertEqual(arcs, {(2, 3), (2, 4)})

    def test_for_else_loop(self):
        code = """
for i in list:
    pass
else:
    print("empty")
end = 1
"""
        arcs = self.get_arcs(code)
        self.assertEqual(arcs, {(2, 3), (2, 5)})

    def test_match_case(self):
        if not hasattr(ast, 'Match'): return
        code = """
match x:
    case 1:
        y = 1
    case 2:
        y = 2
    case _:
        y = 3
z = 4
"""
        arcs = self.get_arcs(code)
        self.assertTrue({(2, 4), (2, 6), (2, 8)}.issubset(arcs))

    def test_match_no_wildcard(self):
        if not hasattr(ast, 'Match'): return
        code = """
match x:
    case 1:
        pass
end = 1
"""
        arcs = self.get_arcs(code)
        self.assertEqual(arcs, {(2, 4), (2, 5)})

    def test_pragma_ignore_branch(self):
        code = """
if x:
    y = 1
else:
    y = 2
"""
        arcs = self.get_arcs(code, ignored={2})
        self.assertEqual(arcs, set())

    def test_function_def_isolation(self):
        code = """
def func():
    if x:
        y = 1
z = 2
"""
        arcs = self.get_arcs(code)
        self.assertEqual(arcs, {(3, 4)})

    def test_nested_loops_and_ifs(self):
        code = """
for i in range(10):
    if i % 2 == 0:
        continue
    x += 1
"""
        arcs = self.get_arcs(code)
        self.assertEqual(arcs, {(2, 3), (3, 4), (3, 5)})

    def test_try_except_finally_ast(self):
        code = """
try:
    if x:
        a = 1
except:
    if y:
        b = 2
finally:
    c = 3
"""
        arcs = self.get_arcs(code)
        self.assertTrue({(3, 4), (6, 7)}.issubset(arcs))
