import unittest
import os
import shutil
import sys
import tempfile
from src.engine import MiniCoverage


class TestMCCScenarios(unittest.TestCase):
    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
        self.cwd = os.getcwd()
        os.chdir(self.test_dir)

    def tearDown(self):
        os.chdir(self.cwd)
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def _run_script(self, code: str, script_name: str = "mcc_test.py"):
        script_path = os.path.join(self.test_dir, script_name)
        with open(script_path, "w") as f:
            f.write(code)
        cov = MiniCoverage(project_root=self.test_dir)
        cov.run(script_path)
        results = cov.analyze()
        canonical = cov.path_manager.canonicalize(script_path)
        return results[canonical].get('MCC', {}).get('missing_outcomes', {})

    def test_mcc_full_coverage(self):
        # For 'a and b', short-circuit paths are:
        # (F, -) -> F
        # (T, F) -> F
        # (T, T) -> T
        code = """
def decision(a, b):
    if a and b: return True
    return False

decision(False, True)
decision(True, False)
decision(True, True)
"""
        missing = self._run_script(code)
        self.assertIn(3, missing)
        self.assertEqual(len(missing[3]['missing']), 0)
        self.assertEqual(missing[3]['ratio'], "3/3")

    def test_mcc_partial_coverage(self):
        code = """
def decision(a, b):
    if a and b: return True
    return False

decision(True, False)
decision(True, True)
"""
        missing = self._run_script(code)
        self.assertEqual(len(missing[3]['missing']), 1)
        self.assertEqual(missing[3]['ratio'], "2/3")
        self.assertEqual(missing[3]['missing'][0]['vector'], ['False', '-'])
        self.assertEqual(missing[3]['missing'][0]['result'], 'False')

    def test_mcc_complex_short_circuit(self):
        code = """
def decision(a, b, c):
    if (a or b) and c:
        return True
    return False

# Short-circuit paths:
# 1. a=T, b=-, c=T -> T
# 2. a=T, b=-, c=F -> F
# 3. a=F, b=T, c=T -> T
# 4. a=F, b=T, c=F -> F
# 5. a=F, b=F, c=- -> F
decision(True, False, True)   # covers path 1
decision(False, False, False) # covers path 5
"""
        missing = self._run_script(code)
        self.assertIn(3, missing)
        self.assertEqual(missing[3]['ratio'], "2/5")
        self.assertEqual(len(missing[3]['missing']), 3)

    @unittest.skipIf(sys.version_info < (3, 14), "TODO: Fix while loop backward jump compiler duplication for Python < 3.14")
    def test_mcc_while_loop_backward_jump(self):
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
        self.assertEqual(missing[3]['ratio'], "3/3")
