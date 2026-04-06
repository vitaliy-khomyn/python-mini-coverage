from .base import TestMetricsBase
from src.metrics import LoopCoverage


class TestLoopCoverage(TestMetricsBase):
    def setUp(self):
        self.metric = LoopCoverage()

    def get_arcs(self, code, ignored=None):
        tree = self.parse_code(code)
        return self.metric.get_possible_elements(tree, ignored or set())

    def test_for_loop(self):
        code = """
for i in range(3):
    print(i)
print("done")
"""
        arcs = self.get_arcs(code)
        # Arc to enter (2->3), arc to skip (2->4)
        self.assertEqual(arcs, {(2, 3), (2, 4)})

    def test_while_loop(self):
        code = """
while x > 0:
    x -= 1
y = 2
"""
        arcs = self.get_arcs(code)
        # Arc to enter (2->3), arc to skip (2->4)
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
        # Arc to enter (2->3), arc to skip to else (2->5)
        self.assertEqual(arcs, {(2, 3), (2, 5)})

    def test_nested_loop(self):
        code = """
for i in range(2):
    while j < 3:
        j += 1
    k = 1
l = 2
"""
        arcs = self.get_arcs(code)
        expected = {
            (2, 3),  # for -> while
            (2, 6),  # for -> l=2
            (3, 4),  # while -> j+=1
            (3, 5),  # while -> k=1
        }
        self.assertEqual(arcs, expected)

    def test_loop_in_function(self):
        code = """
def my_func():
    for i in range(1):
        return
    print("end")
"""
        arcs = self.get_arcs(code)
        # Arc to enter (3->4), arc to skip (3->5)
        self.assertEqual(arcs, {(3, 4), (3, 5)})
