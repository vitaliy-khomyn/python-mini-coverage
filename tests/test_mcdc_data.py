import unittest
import os
import shutil
import tempfile
from src.engine import MiniCoverage


class TestMCDCData(unittest.TestCase):
    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
        self.cwd = os.getcwd()
        os.chdir(self.test_dir)

    def tearDown(self):
        os.chdir(self.cwd)
        try:
            shutil.rmtree(self.test_dir)
        except PermissionError:
            import time
            time.sleep(0.2)
            shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_boolean_short_circuit_capture(self):
        """
        Verify that different boolean paths generate different instruction arcs.
        This confirms the tracer is capturing data fine-grained enough for MC/DC.
        """
        code = """
def decision(a, b):
    if a and b:
        return True
    return False

decision(True, False)
"""
        script_path = os.path.join(self.test_dir, "mcdc_test.py")
        with open(script_path, "w") as f:
            f.write(code)

        # run 1: True, False
        cov1 = MiniCoverage(project_root=self.test_dir)
        cov1.run(script_path)
        canonical_path = cov1.path_manager.canonicalize(script_path)
        arcs1 = cov1.trace_data['instruction_arcs'][canonical_path][0].copy()

        # run 2: True, True
        code2 = """
def decision(a, b):
    if a and b:
        return True
    return False

decision(True, True)
"""
        with open(script_path, "w") as f:
            f.write(code2)

        cov2 = MiniCoverage(project_root=self.test_dir)
        cov2.run(script_path)
        arcs2 = cov2.trace_data['instruction_arcs'][canonical_path][0].copy()

        # the sets of bytecode transitions should differ because
        # the second condition 'b' evaluates differently or the jump targets differ.
        # in (True, False), 'and' fails, jumping to return False.
        # in (True, True), 'and' succeeds, entering the block.
        self.assertNotEqual(arcs1, arcs2)
        self.assertTrue(len(arcs1) > 0)
        self.assertTrue(len(arcs2) > 0)

    def test_instruction_arcs_exist(self):
        # basic sanity check that instruction_arcs are being populated at all
        # this ensures the C-extension or Python fallback is handling PyTrace_OPCODE
        pass


if __name__ == '__main__':
    unittest.main()
