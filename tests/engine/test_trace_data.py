import unittest
from src.engine.trace_data import TraceContainer, TraceDataType


class TestTraceData(unittest.TestCase):
    def setUp(self):
        self.container = TraceContainer()

    def test_add_line(self):
        self.container.add_line("test.py", 0, 10)
        self.assertIn(10, self.container[TraceDataType.LINES]["test.py"][0])
        self.container.add_line("test.py", 0, 15)
        self.assertIn(15, self.container[TraceDataType.LINES]["test.py"][0])

    def test_add_arc(self):
        self.container.add_arc("test.py", 0, 10, 11)
        self.assertIn((10, 11), self.container[TraceDataType.ARCS]["test.py"][0])

    def test_add_instruction_arc(self):
        self.container.add_instruction_arc("test.py", 0, 1, 10, 12)
        self.assertIn((1, 10, 12), self.container[TraceDataType.INSTRUCTION_ARCS]["test.py"][0])

    def test_default_initialization(self):
        # Accessing nested structures should automatically initialize them as sets
        empty_lines = self.container[TraceDataType.LINES]["new_file.py"][1]
        self.assertEqual(len(empty_lines), 0)
        self.assertIsInstance(empty_lines, set)
