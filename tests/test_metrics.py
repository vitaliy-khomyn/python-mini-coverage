import unittest
import ast
from src.metrics import StatementCoverage, BranchCoverage, ConditionCoverage


class TestMetricsBase(unittest.TestCase):
    def parse_code(self, code):
        return ast.parse(code)


class TestStatementCoverage(TestMetricsBase):
    def setUp(self):
        self.metric = StatementCoverage()

    def test_simple_assignments(self):
        code = """
x = 1
y = 2
z = x + y
"""
        tree = self.parse_code(code)
        lines = self.metric.get_possible_elements(tree, set())
        self.assertEqual(lines, {2, 3, 4})

    def test_ignore_docstrings(self):
        code = """
'This is a docstring'
x = 1
'''
Another docstring
'''
y = 2
"""
        tree = self.parse_code(code)
        lines = self.metric.get_possible_elements(tree, set())
        # Line 2 and 4-6 are docstrings, should only have 3 and 7
        self.assertEqual(lines, {3, 7})

    def test_ignore_constants(self):
        code = """
x = 1
'standalone string'
123
y = 2
"""
        tree = self.parse_code(code)
        lines = self.metric.get_possible_elements(tree, set())
        # Line 3 is a string constant. Line 4 is a number constant.
        # Both should be ignored.
        self.assertEqual(lines, {2, 5})

    def test_pragma_ignore(self):
        code = """
x = 1
y = 2
z = 3
"""
        tree = self.parse_code(code)
        # Simulate pragma on line 3
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
        # Line 2: if
        # Line 3: y=1 (True body)
        # Line 4: z=2 (Implicit False / Fallthrough)
        arcs = self.get_arcs(code)
        expected = {(2, 3), (2, 4)}
        self.assertEqual(arcs, expected)

    def test_if_else(self):
        code = """
if x:
    y = 1
else:
    y = 2
z = 3
"""
        # 2->3 (True), 2->5 (False)
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
        # if x: 2->3 (T), 2->4 (F -> elif)
        # elif y: 4->5 (T), 4->7 (F -> else)
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
        # Outer: 2->3 (T), 2->6 (F)
        # Inner: 3->4 (T), 3->5 (F -> b=2)
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
        # 2->3 (Enter), 2->4 (Exit)
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
        # 2->3 (Enter)
        # 2->5 (Exit/Else)
        arcs = self.get_arcs(code)
        self.assertEqual(arcs, {(2, 3), (2, 5)})

    def test_match_case(self):
        # Python 3.10+ syntax
        if not hasattr(ast, 'Match'):
            return

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
        if not hasattr(ast, 'Match'):
            return

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
        # If line 2 is ignored, no arcs should come from it
        arcs = self.get_arcs(code, ignored={2})
        self.assertEqual(arcs, set())

    def test_function_def_isolation(self):
        code = """
def func():
    if x:
        y = 1
z = 2
"""
        # Function def at 2. Body at 3.
        # 'z=2' is at 5.
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


class TestConditionCoverage(TestMetricsBase):
    def setUp(self):
        self.metric = ConditionCoverage()

    def get_conditions(self, code, ignored=None):
        ignored = ignored or set()
        tree = self.parse_code(code)
        return self.metric.get_possible_elements(tree, ignored)

    def test_simple_and(self):
        code = "if a and b:\n    pass"
        conditions = self.get_conditions(code)
        self.assertEqual(len(conditions), 2)
        lines = {c[0] for c in conditions}
        self.assertEqual(lines, {1})

    def test_mixed_bool_ops(self):
        code = "res = (a or b) and c"
        # AST: BoolOp(and, values=[BoolOp(or, values=[a, b]), c])
        # We now use (lineno, col, type) so we should differentiate:
        # 1. 'a' (Name)
        # 2. 'b' (Name)
        # 3. 'a or b' (BoolOp) - this is a value in the outer AND
        # 4. 'c' (Name)
        # Total = 4 distinct conditions
        conditions = self.get_conditions(code)
        self.assertEqual(len(conditions), 4)

    def test_no_conditions(self):
        code = "x = 1"
        conditions = self.get_conditions(code)
        self.assertEqual(len(conditions), 0)