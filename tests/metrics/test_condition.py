from src.metrics import ConditionCoverage
from .base import TestMetricsBase


class TestConditionCoverage(TestMetricsBase):
    def setUp(self):
        self.metric = ConditionCoverage()

    def get_conditions(self, code, ignored=None):
        ignored = ignored or set()
        # FIX: Use compile_code for Bytecode/MC/DC analysis
        co = self.compile_code(code)
        return self.metric.get_possible_elements(co, ignored)

    def test_simple_and(self):
        code = "if a and b:\n    pass"
        conditions = self.get_conditions(code)
        # Expecting at least one boolean jump pair (2 arcs) per boolean op
        # 'a and b' compiles to JUMP_IF_FALSE (or similar)
        self.assertGreaterEqual(len(conditions), 2)

    def test_mixed_bool_ops(self):
        code = "res = (a or b) and c"
        conditions = self.get_conditions(code)
        # Should detect jumps for OR and AND
        self.assertGreater(len(conditions), 0)

    def test_no_conditions(self):
        code = "x = 1"
        conditions = self.get_conditions(code)
        self.assertEqual(len(conditions), 0)

    def test_multiline_conditions(self):
        code = """
if (a and
    b):
    pass
"""
        conditions = self.get_conditions(code)
        self.assertGreater(len(conditions), 0)
