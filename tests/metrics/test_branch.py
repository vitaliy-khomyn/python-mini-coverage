import ast
import sys

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

    def test_with_statement(self):
        code = """
with open('f') as f:
    if x:
        y = 1
z = 2
"""
        arcs = self.get_arcs(code)
        self.assertEqual(arcs, {(3, 4), (3, 5)})

    def test_async_with_statement(self):
        code = """
async def func():
    async with lock:
        if x:
            y = 1
    z = 2
"""
        arcs = self.get_arcs(code)
        self.assertEqual(arcs, {(4, 5), (4, 6)})

    def test_try_except_else_finally_nested_ifs(self):
        code = """
try:
    pass
except:
    if y:
        b = 2
else:
    if z:
        c = 3
finally:
    if w:
        d = 4
"""
        arcs = self.get_arcs(code)
        self.assertTrue({(5, 6), (8, 9), (11, 12)}.issubset(arcs))

    def test_inline_if_expression_ignored(self):
        # BranchCoverage operates on statement-level control flow,
        # so inline expressions like IfExp are not tracked as branches here.
        code = "x = 1 if y else 2"
        arcs = self.get_arcs(code)
        self.assertEqual(arcs, set())

    def test_chained_comparison(self):
        code = "if 1 < x < 10:\n    pass"
        arcs = self.get_arcs(code)
        self.assertEqual(arcs, {(1, 2)})

    def test_walrus_operator(self):
        if sys.version_info < (3, 8):
            return
        code = "if (n := get()) > 0:\n    pass"
        arcs = self.get_arcs(code)
        self.assertEqual(arcs, {(1, 2)})

    def test_async_condition(self):
        code = "async def func():\n    if await cond():\n        pass"
        arcs = self.get_arcs(code)
        self.assertEqual(arcs, {(2, 3)})

    def test_generator_condition(self):
        code = "if next(gen):\n    pass"
        arcs = self.get_arcs(code)
        self.assertEqual(arcs, {(1, 2)})

    def test_comprehension_filter(self):
        code = "[x for x in values if x > 0]"
        arcs = self.get_arcs(code)
        # Comprehensions are typically ignored by standard branch coverage unless explicitly mapped
        self.assertEqual(arcs, set())

    def test_boolean_assignment(self):
        code = "x = [] or [1]"
        arcs = self.get_arcs(code)
        self.assertEqual(arcs, set())

    def test_exception_interruption(self):
        code = "if explode() and x:\n    pass"
        arcs = self.get_arcs(code)
        self.assertEqual(arcs, {(1, 2)})
