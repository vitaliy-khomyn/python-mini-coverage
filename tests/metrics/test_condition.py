from src.metrics import ConditionCoverage
from .base import TestMetricsBase


class TestConditionCoverage(TestMetricsBase):
    def setUp(self):
        self.metric = ConditionCoverage()

    def get_conditions(self, code, ignored=None):
        ignored = ignored or set()
        tree = self.parse_code(code)
        self.metric.set_ast(tree)
        co = self.compile_code(code)
        return self.metric.get_possible_elements(co, ignored)

    def test_simple_and(self):
        code = "if a and b:\n    pass"
        conditions = self.get_conditions(code)
        # 2 operands * 2 arcs (jump/fallthrough) = 4 arcs
        self.assertEqual(len(conditions), 4)

    def test_mixed_bool_ops(self):
        code = "if (a or b) and c:\n    pass"
        conditions = self.get_conditions(code)
        # 3 operands * 2 arcs = 6 arcs
        self.assertEqual(len(conditions), 6)

    def test_no_conditions(self):
        code = "x = 1"
        conditions = self.get_conditions(code)
        self.assertEqual(len(conditions), 0)

    def test_single_condition(self):
        code = "if a:\n    pass"
        conditions = self.get_conditions(code)
        # 1 operand * 2 arcs = 2 arcs
        self.assertEqual(len(conditions), 2)

    def test_multiline_conditions(self):
        code = """
if (a and
    b):
    pass
"""
        conditions = self.get_conditions(code)
        # 2 operands * 2 arcs = 4 arcs
        self.assertEqual(len(conditions), 4)

    def test_ignore_function_signatures_compiler_artifacts(self):
        code = """
def outer(a: bool) -> bool:
    b: bool = True
    def inner(c: bool) -> bool:
        if a and c:
            return True
        return False
    return inner(b)
"""
        conditions = self.get_conditions(code)
        print(conditions)
        # Only the 'if a and c:' line contains actual boolean logic.
        # The AST mask prevents compiler artifacts on the 'def' lines from being counted.
        # An 'and' operator with two operands creates exactly 4 target arcs (jump/fallthrough for each operand).
        self.assertEqual(len(conditions), 4)

    def test_complex_condition_if(self):
        code = """
if (a or b) and (c or d) and e:
    pass
"""
        conditions = self.get_conditions(code)
        # 5 operands in 'if' statement.
        # Every operand must generate a jump to decide whether to enter the 'if' block.
        # 5 * 2 arcs = 10 arcs
        self.assertEqual(len(conditions), 10)

    def test_complex_condition_assignment(self):
        code = "result = (a or b) and (c or d) and e"
        conditions = self.get_conditions(code)
        # 5 operands in assignment.
        # The final evaluation 'e' leaves its value on the stack to be assigned,
        # generating no jump instruction for 'e' itself.
        # 4 jumping operands * 2 arcs = 8 arcs
        self.assertEqual(len(conditions), 8)
