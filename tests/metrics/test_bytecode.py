from src.metrics import BytecodeControlFlow
from .base import TestMetricsBase


class TestBytecodeMetric(TestMetricsBase):
    def setUp(self):
        self.metric = BytecodeControlFlow()

    def test_jumps_identification(self):
        code = "if x: pass\nelse: pass"
        co = self.compile_code(code)
        jumps = self.metric.get_possible_elements(co)
        self.assertGreater(len(jumps), 0)
