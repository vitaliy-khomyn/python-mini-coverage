import unittest
import os
import shutil
import sys
import tempfile
from src.engine import MiniCoverage


class TestMCDCScenarios(unittest.TestCase):
    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
        self.cwd = os.getcwd()
        os.chdir(self.test_dir)

    def tearDown(self):
        os.chdir(self.cwd)
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def _run_script(self, code: str, script_name: str = "mcdc_test.py"):
        script_path = os.path.join(self.test_dir, script_name)
        with open(script_path, "w") as f:
            f.write(code)
        cov = MiniCoverage(project_root=self.test_dir)
        cov.run(script_path)
        results = cov.analyze()
        canonical = cov.path_manager.canonicalize(script_path)
        return results[canonical].get('MMC/DC', {}).get('missing_outcomes', {})

    def test_mcdc_full_coverage(self):
        # N+1 test cases can achieve 100% MC/DC for N variables.
        code = """
def decision(a, b):
    if a and b: return True
    return False

decision(False, True)  # A=F, B=T -> False
decision(True, False)  # A=T, B=F -> False
decision(True, True)   # A=T, B=T -> True
"""
        missing = self._run_script(code)

        # Line 3 is the 'if a and b:' statement
        self.assertIn(3, missing)
        # Both conditions 'a' and 'b' have proven independent effect, missing = 0
        self.assertEqual(len(missing[3]['missing']), 0)
        self.assertEqual(missing[3]['ratio'], "2/2")

    def test_mcdc_partial_coverage(self):
        code = """
def decision(a, b):
    if a and b: return True
    return False

decision(True, False)  # A=T, B=F -> False
decision(True, True)   # A=T, B=T -> True
"""
        missing = self._run_script(code)

        # In these 2 tests, 'a' is ALWAYS True. It never independently changed the outcome!
        # Therefore, condition 1 ('a') should be missing MC/DC.
        # Condition 2 ('b') changed from F to T, outcome changed F to T. It is covered.
        self.assertEqual(len(missing[3]['missing']), 1)
        self.assertIn("'a'", missing[3]['missing'][0]['message'])
        self.assertEqual(missing[3]['ratio'], "1/2")

    def test_mcdc_vs_condition_coverage(self):
        """
        Showcase test demonstrating the precise difference between Condition Coverage and MC/DC.
        Provides a test set that achieves 100% Condition Coverage but fails MC/DC.
        """
        code = """
def decision(a, b, c):
    if (a or b) and c:
        return True
    return False

# V2: a=F, b=T, c=T -> True
decision(False, True, True)

# V3: a=F, b=F, c=F -> False (c is masked by b=F)
decision(False, False, False)

# V4: a=T, b=F, c=F -> False (b is masked by a=T)
decision(True, False, False)

# V5: a=F, b=T, c=F -> False
decision(False, True, False)
"""
        script_path = os.path.join(self.test_dir, "mcdc_vs_cond.py")
        with open(script_path, "w") as f:
            f.write(code)

        cov = MiniCoverage(project_root=self.test_dir)
        cov.run(script_path)
        results = cov.analyze()
        canonical = cov.path_manager.canonicalize(script_path)

        cond_stats = results[canonical].get('Condition', {}).get('missing_outcomes', {})
        mcdc_stats = results[canonical].get('MMC/DC', {}).get('missing_outcomes', {})

        # Line 3 is the 'if (a or b) and c:' statement
        self.assertIn(3, cond_stats)
        self.assertIn(3, mcdc_stats)

        # 100% Condition Coverage: All possible terminal outcomes were executed
        self.assertEqual(cond_stats[3]['ratio'], "4/4", "Condition Coverage should be 100%")
        self.assertEqual(len(cond_stats[3]['missing']), 0)

        # With True Contiguous Path tracing, MMC/DC correctly sees that condition 1 ('a')
        # is not proven because condition 3 ('c') changes simultaneously between the
        # independent tests for 'a'.
        self.assertEqual(mcdc_stats[3]['ratio'], "2/3")
        self.assertEqual(len(mcdc_stats[3]['missing']), 1)
        self.assertIn("'a' independent effect not proven", mcdc_stats[3]['missing'][0]['message'])

    def test_mcdc_100_percent_achievable(self):
        """
        Demonstrates that by providing the correct independence pairs,
        the exact same decision from the previous test can achieve 100% MC/DC.
        """
        code = """
def decision(a, b, c):
    if (a or b) and c:
        return True
    return False

# Pair for A:
decision(True, False, True)   # Vector: [T, -, T] -> True
decision(False, False, True)  # Vector: [F, F, -] -> False

# Pair for B:
decision(False, True, True)   # Vector: [F, T, T] -> True
# decision(False, False, True) from above acts as the False outcome for B

# Pair for C:
# decision(False, True, True) from above acts as the True outcome for C
decision(False, True, False)  # Vector: [F, T, F] -> False
"""
        script_path = os.path.join(self.test_dir, "mcdc_100.py")
        with open(script_path, "w") as f:
            f.write(code)

        cov = MiniCoverage(project_root=self.test_dir)
        cov.run(script_path)
        results = cov.analyze()
        canonical = cov.path_manager.canonicalize(script_path)

        cond_stats = results[canonical].get('Condition', {}).get('missing_outcomes', {})
        mcdc_stats = results[canonical].get('MMC/DC', {}).get('missing_outcomes', {})

        self.assertEqual(cond_stats[3]['ratio'], "4/4", "Condition Coverage should still be 100%")

        self.assertEqual(mcdc_stats[3]['ratio'], "3/3", "MC/DC should now be 100% with valid pairs")
        self.assertEqual(len(mcdc_stats[3]['missing']), 0)

    def test_instrumentation_does_not_double_evaluate(self):
        code = """
counter = 0

def cond():
    global counter
    counter += 1
    return True

if cond():
    pass

assert counter == 1
"""
        # Should run without AssertionError
        missing = self._run_script(code)
        self.assertIn(9, missing)

    def test_truthiness_semantics(self):
        code = """
class Weird:
    def __bool__(self):
        return True

if Weird():
    pass
"""
        missing = self._run_script(code)
        self.assertIn(6, missing)
        self.assertEqual(missing[6]['ratio'], "0/1")

    def test_mcdc_nested_expressions(self):
        code = """
def decision(a, b, c, d):
    if (a and b) or (c and not d):
        return True
    return False

decision(True, True, False, False)
decision(True, False, True, False)
decision(False, True, False, False)
decision(True, False, False, False)
decision(False, False, True, True)
"""
        missing = self._run_script(code)
        self.assertIn(3, missing)

    def test_mcdc_repeated_conditions(self):
        code = """
def decision(a, b):
    if a and (a or b):
        pass

decision(True, False)
decision(False, True)
"""
        missing = self._run_script(code)
        self.assertIn(3, missing)

    def test_mcdc_masked_condition(self):
        code = """
def decision(a, b):
    if a or (a and b):
        pass

decision(True, False)
decision(False, True)
"""
        missing = self._run_script(code)
        self.assertIn(3, missing)
        # Because a and b is masked when a is True, b can't be independently evaluated.
        self.assertGreater(len(missing[3]['missing']), 0)

    def test_mcdc_coupled_conditions(self):
        code = """
def decision(x):
    if (x > 0) and (x > -1):
        pass

decision(1)
decision(-2)
"""
        missing = self._run_script(code)
        self.assertIn(3, missing)

    def test_mcdc_exception_interruption(self):
        code = """
def explode():
    raise ValueError()

try:
    if explode() and True:
        pass
except ValueError:
    pass
"""
        missing = self._run_script(code)
        self.assertIn(6, missing)

    def test_mcc_explosion(self):
        code = """
def decision(a, b, c, d, e, f):
    if a and b and c and d and e and f:
        pass

decision(True, True, True, True, True, True)
decision(False, True, True, True, True, True)
"""
        missing = self._run_script(code)
        self.assertIn(3, missing)

    @unittest.skipIf(sys.version_info < (3, 14), "TODO: Fix while loop backward jump compiler duplication for Python < 3.14")
    def test_mcdc_while_loop_backward_jump(self):
        code = """
def loop_decision(a, b):
    while a and b:
        b = False
    return a

loop_decision(True, True)
loop_decision(False, True)
"""
        missing = self._run_script(code)
        self.assertIn(3, missing)
        self.assertEqual(missing[3]['ratio'], "2/2")
