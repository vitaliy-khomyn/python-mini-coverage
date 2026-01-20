import unittest
import os
import shutil
import tempfile
import types
from src.engine import MiniCoverage
from src.metrics.condition import ConditionCoverage


class TestConditionCoverageScenarios(unittest.TestCase):
    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
        self.cwd = os.getcwd()
        os.chdir(self.test_dir)

    def tearDown(self):
        os.chdir(self.cwd)
        try:
            shutil.rmtree(self.test_dir)
        except PermissionError:
            pass

    def test_condition_full_coverage(self):
        """
        Verify Condition Coverage logic on 'a and (b or c)' with a minimal passing set (4 cases).
        """
        code = """
def full_condition(a, b, c):
    if a and (b or c):
        return True
    return False

# 1. Full Condition Coverage (4 cases out of 8 possible)
# a=False (Masks b, c)
full_condition(False, True, True)

# a=True, b=True (Masks c)
full_condition(True, True, False)

# a=True, b=False, c=True
full_condition(True, False, True)

# a=True, b=False, c=False
full_condition(True, False, False)

"""
        script_path = os.path.join(self.test_dir, "condition_full.py")
        with open(script_path, "w") as f:
            f.write(code)

        # Run coverage
        cov = MiniCoverage(project_root=self.test_dir)
        cov.run(script_path)

        # Analyze results
        canonical_path = cov.path_manager.canonicalize(script_path)
        executed_arcs = set()
        for raw_path, ctx_map in cov.trace_data['instruction_arcs'].items():
            if cov.path_manager.canonicalize(raw_path) == canonical_path:
                for arcs in ctx_map.values():
                    executed_arcs.update(arcs)

        # Compile to get code objects
        co = compile(code, script_path, 'exec')
        func_code = None
        for const in co.co_consts:
            if isinstance(const, types.CodeType) and const.co_name == 'full_condition':
                func_code = const
                break

        metric = ConditionCoverage()
        possible = metric.get_possible_elements(func_code)
        stats = metric.calculate_stats(possible, executed_arcs)

        self.assertEqual(stats['pct'], 100.0,
                         f"Expected 100% Condition Coverage for minimal set, got {stats['pct']}%")
        self.assertEqual(len(stats['missing']), 0)

    def test_condition_partial_coverage(self):
        """
        Verify Condition Coverage logic on 'a and (b or c)' with a partial set missing exactly one outcome (a=False).
        """
        code = """
def partial_condition(a, b, c):
    # a and (b or c)
    if a and (b or c):
        return True
    return False

# 2. Partial Condition Coverage (Missing a=False case)
partial_condition(True, True, False)
partial_condition(True, False, True)
partial_condition(True, False, False)
"""
        script_path = os.path.join(self.test_dir, "condition_partial.py")
        with open(script_path, "w") as f:
            f.write(code)

        # Run coverage
        cov = MiniCoverage(project_root=self.test_dir)
        cov.run(script_path)

        # Analyze results
        canonical_path = cov.path_manager.canonicalize(script_path)
        executed_arcs = set()
        for raw_path, ctx_map in cov.trace_data['instruction_arcs'].items():
            if cov.path_manager.canonicalize(raw_path) == canonical_path:
                for arcs in ctx_map.values():
                    executed_arcs.update(arcs)

        # Compile to get code objects
        co = compile(code, script_path, 'exec')
        func_code = None
        for const in co.co_consts:
            if isinstance(const, types.CodeType) and const.co_name == 'partial_condition':
                func_code = const
                break

        metric = ConditionCoverage()
        possible = metric.get_possible_elements(func_code)
        stats = metric.calculate_stats(possible, executed_arcs)

        self.assertLess(stats['pct'], 100.0, "Partial set should not have 100% coverage")

        missing_map = metric.map_missing_arcs(func_code, stats['missing'])

        # Extract vectors from the detailed stats structure returned by map_missing_arcs
        missing_vectors = [m['vector'] for line_stats in missing_map.values() for m in line_stats.get('missing', [])]
        self.assertTrue(any(v.startswith('False') for v in missing_vectors),
                      f"Should report missing 'False' outcome for condition 'a'. Got: {missing_map}")


if __name__ == '__main__':
    unittest.main()
