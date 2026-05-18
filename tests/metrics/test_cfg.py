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

    def test_cfg_raise_no_fallthrough(self):
        code = """
raise ValueError()
x = 1
"""
        cfg = self.build_cfg(code)
        # RAISE_VARARGS is an unconditional flow breaker. It should have 0 successors
        # (unless there is an exception handler, which there isn't here).
        self.assertEqual(len(cfg.successors[0]), 0)

    def test_cfg_break_edge(self):
        code = """
for i in range(2):
    break
"""
        cfg = self.build_cfg(code)
        jumps = cfg.get_jumps()
        # 'break' causes a forward jump out of the loop
        has_forward_jump = any(src < tgt for src, tgt in jumps)
        self.assertTrue(has_forward_jump, "Break should generate a forward jump edge")

    def test_cfg_continue_edge(self):
        code = """
for i in range(2):
    continue
"""
        cfg = self.build_cfg(code)
        jumps = cfg.get_jumps()
        # 'continue' causes a backward jump or an absolute jump to the loop header
        self.assertGreater(len(jumps), 0, "Continue should generate at least one jump edge")

    def test_cfg_yield_fallthrough(self):
        code = """
def gen():
    yield 1
    yield 2
"""
        co = self.compile_code(code)
        gen_co = next(c for c in co.co_consts if isinstance(c, types.CodeType) and c.co_name == 'gen')
        cfg = ControlFlowGraph(gen_co)
        # YIELD_VALUE is not an unconditional flow breaker, so it shouldn't sever the CFG entirely.
        # Depending on the Python version, it might create a block or just fall through.
        self.assertGreaterEqual(len(cfg.blocks), 1)
