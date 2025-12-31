import types
from src.metrics import ControlFlowGraph
from .base import TestMetricsBase


class TestControlFlowGraph(TestMetricsBase):
    def build_cfg(self, source_code):
        co = self.compile_code(source_code)
        return ControlFlowGraph(co)

    def test_leaders_simple(self):
        code = "x = 1\ny = 2\nprint(x)"
        cfg = self.build_cfg(code)
        self.assertIn(0, cfg.leaders)
        self.assertEqual(len(cfg.blocks), 1)

    def test_leaders_branching(self):
        code = """
if x:
    y = 1
else:
    y = 2
"""
        cfg = self.build_cfg(code)
        self.assertGreaterEqual(len(cfg.blocks), 3)

    def test_edges_if_else(self):
        code = "if x: y=1\nelse: y=2\nz=3"
        cfg = self.build_cfg(code)
        start_succ = cfg.successors[0]
        self.assertEqual(len(start_succ), 2)

    def test_edges_loop(self):
        code = "for i in range(3): print(i)"
        cfg = self.build_cfg(code)
        has_back_edge = False
        for src, targets in cfg.successors.items():
            for t in targets:
                if t <= src:
                    has_back_edge = True
        self.assertTrue(has_back_edge, "Loop should have back-edge")

    def test_dominators_linear(self):
        code = "x=1\ny=2"
        cfg = self.build_cfg(code)
        self.assertEqual(cfg.dominators[0], {0})

    def test_dominators_diamond(self):
        code = """
if x:
    a = 1
else:
    a = 2
z = 3
"""
        cfg = self.build_cfg(code)
        for node, doms in cfg.dominators.items():
            self.assertIn(0, doms)

        last_block_start = cfg.blocks[-1][0]
        if last_block_start != 0:
            self.assertIn(0, cfg.dominators[last_block_start])

    def test_cfg_exception_handler(self):
        code = """
try:
    x = 1 / 0
except ZeroDivisionError:
    y = 2
"""
        cfg = self.build_cfg(code)
        self.assertGreaterEqual(len(cfg.blocks), 2)

    def test_cfg_with_return(self):
        code = """
def foo():
    if x:
        return 1
    return 2
"""
        module_co = self.compile_code(code)
        foo_co = None
        for const in module_co.co_consts:
            if isinstance(const, types.CodeType) and const.co_name == 'foo':
                foo_co = const
                break

        self.assertIsNotNone(foo_co)
        cfg = ControlFlowGraph(foo_co)
        self.assertGreater(len(cfg.blocks), 1)

    def test_cfg_infinite_loop(self):
        code = "while True: pass"
        cfg = self.build_cfg(code)
        self.assertGreater(len(cfg.successors), 0)
