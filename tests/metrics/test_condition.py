import sys

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

    def test_chained_comparison(self):
        code = "if 1 < x < 10:\n    pass"
        conditions = self.get_conditions(code)
        self.assertEqual(len(conditions), 4)

    def test_walrus_operator(self):
        if sys.version_info < (3, 8):
            return
        code = "if (n := get()) > 0:\n    pass"
        conditions = self.get_conditions(code)
        self.assertEqual(len(conditions), 2)

    def test_async_condition(self):
        code = "async def func():\n    if await cond():\n        pass"
        conditions = self.get_conditions(code)
        self.assertEqual(len(conditions), 2)

    def test_generator_condition(self):
        code = "if next(gen):\n    pass"
        conditions = self.get_conditions(code)
        self.assertEqual(len(conditions), 2)

    def test_comprehension_filter(self):
        code = "[x for x in values if x > 0]"
        conditions = self.get_conditions(code)
        self.assertEqual(len(conditions), 2)

    def test_boolean_assignment(self):
        code = "x = [] or [1]"
        conditions = self.get_conditions(code)
        self.assertEqual(len(conditions), 2)

    def test_truthiness_class(self):
        code = "class Weird:\n    def __bool__(self):\n        return True\nif Weird():\n    pass"
        conditions = self.get_conditions(code)
        self.assertEqual(len(conditions), 2)

    def test_exception_interruption(self):
        code = "if explode() and x:\n    pass"
        conditions = self.get_conditions(code)
        self.assertEqual(len(conditions), 4)

    def test_dynamic_attribute_lookup(self):
        code = "if x.foo:\n    pass"
        conditions = self.get_conditions(code)
        self.assertEqual(len(conditions), 2)

    def test_property_side_effects(self):
        code = "if x.value:\n    pass"
        conditions = self.get_conditions(code)
        self.assertEqual(len(conditions), 2)

    def test_mcc_explosion(self):
        code = "if a and b and c and d and e and f:\n    pass"
        conditions = self.get_conditions(code)
        self.assertEqual(len(conditions), 12)
