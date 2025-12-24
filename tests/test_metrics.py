import unittest
import ast
import types
import sys
import dis
from src.metrics import (
    StatementCoverage,
    BranchCoverage,
    ConditionCoverage,
    BytecodeControlFlow,
    ControlFlowGraph
)


class TestMetricsBase(unittest.TestCase):
    def parse_code(self, code):
        return ast.parse(code)

    def compile_code(self, code):
        return compile(code, "<string>", "exec")


# --- Statement Coverage Tests ---

class TestStatementCoverage(TestMetricsBase):
    def setUp(self):
        self.metric = StatementCoverage()

    def test_simple_assignments(self):
        code = "x = 1\ny = 2\nz = x + y"
        tree = self.parse_code(code)
        lines = self.metric.get_possible_elements(tree, set())
        self.assertEqual(lines, {1, 2, 3})

    def test_ignore_docstrings_and_constants(self):
        code = """
'docstring'
x = 1
123 # constant number
y = 2
"""
        tree = self.parse_code(code)
        lines = self.metric.get_possible_elements(tree, set())
        self.assertEqual(lines, {3, 5})

    def test_pragma_ignore(self):
        code = """
x = 1
y = 2
z = 3
"""
        tree = self.parse_code(code)
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

    def test_async_functions(self):
        code = """
async def fetch():
    x = 1
    await foo()
"""
        tree = self.parse_code(code)
        lines = self.metric.get_possible_elements(tree, set())
        self.assertTrue({2, 3, 4}.issubset(lines))

    def test_decorators(self):
        code = """
@decorator
def func():
    pass
"""
        tree = self.parse_code(code)
        lines = self.metric.get_possible_elements(tree, set())
        # Function def is line 3. Body is line 4.
        self.assertIn(3, lines)
        self.assertIn(4, lines)

    def test_walrus_operator(self):
        if sys.version_info < (3, 8): return
        code = """
if (x := 1) > 0:
    y = 2
"""
        tree = self.parse_code(code)
        lines = self.metric.get_possible_elements(tree, set())
        self.assertEqual(lines, {2, 3})

    def test_annotated_assignments(self):
        code = """
x: int = 1
y: str
"""
        tree = self.parse_code(code)
        lines = self.metric.get_possible_elements(tree, set())
        self.assertIn(2, lines)


# --- Branch Coverage Tests ---

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


# --- Control Flow Graph & Bytecode Tests ---

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


class TestBytecodeMetric(TestMetricsBase):
    def setUp(self):
        self.metric = BytecodeControlFlow()

    def test_jumps_identification(self):
        code = "if x: pass\nelse: pass"
        co = self.compile_code(code)
        jumps = self.metric.get_possible_elements(co)
        self.assertGreater(len(jumps), 0)