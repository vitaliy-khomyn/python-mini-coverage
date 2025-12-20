from src.engine import MiniCoverage
from tests.test_utils import BaseTestCase


class TestIntegration(BaseTestCase):

    def test_run_simple_script(self):
        script_content = """
x = 1
if x > 0:
    print("hit")
else:
    print("miss")
"""
        script_path = self.create_file("simple.py", script_content)

        cov = MiniCoverage(project_root=self.test_dir)

        # Capture stdout to suppress script output
        with self.capture_stdout():
            cov.run(script_path)

        results = cov.analyze()
        file_res = results[script_path]

        # Check Statements
        # Lines: 2, 3, 4 (hit), 6 (miss)
        # 'else' (5) is usually not executable statement in AST,
        # but the print(miss) at 6 is.
        stmt = file_res['Statement']
        self.assertIn(6, stmt['missing'])
        self.assertIn(4, stmt['executed'])

        # Check Branches
        # 3->4 (taken), 3->6 (missed)
        branch = file_res['Branch']
        self.assertIn((3, 6), branch['missing'])

    def test_run_with_exception(self):
        script_content = """
try:
    raise ValueError("boom")
except ValueError:
    print("caught")
"""
        script_path = self.create_file("ex.py", script_content)
        cov = MiniCoverage(project_root=self.test_dir)

        with self.capture_stdout():
            cov.run(script_path)

        results = cov.analyze()
        stmt = results[script_path]['Statement']
        # All lines should be hit
        self.assertEqual(len(stmt['missing']), 0)

    def test_run_recursion(self):
        script_content = """
def fact(n):
    if n <= 1:
        return 1
    return n * fact(n-1)
fact(3)
"""
        script_path = self.create_file("recur.py", script_content)
        cov = MiniCoverage(project_root=self.test_dir)

        with self.capture_stdout():
            cov.run(script_path)

        results = cov.analyze()
        stmt = results[script_path]['Statement']
        self.assertEqual(len(stmt['missing']), 0)

    def test_concurrency_integration(self):
        # This tests that threads are actually traced
        script_content = """
import threading
def worker():
    x = 1 + 1
t = threading.Thread(target=worker)
t.start()
t.join()
"""
        script_path = self.create_file("threads.py", script_content)
        cov = MiniCoverage(project_root=self.test_dir)

        with self.capture_stdout():
            cov.run(script_path)

        results = cov.analyze()
        # If threading support was broken, line 4 (x=1+1) would be missing
        stmt = results[script_path]['Statement']
        self.assertNotIn(4, stmt['missing'])

    def test_multiprocessing_patch(self):
        # NOTE: Testing multiprocessing with settrace in a subprocess in a unit test
        # is complex and prone to environment issues.
        # We perform a lightweight check: ensure the patch flag is set.

        script_content = "import multiprocessing; print(multiprocessing)"
        script_path = self.create_file("mp.py", script_content)
        cov = MiniCoverage(project_root=self.test_dir)

        with self.capture_stdout():
            cov.run(script_path)

        import multiprocessing
        self.assertTrue(hasattr(multiprocessing, '_mini_coverage_patched'))

    def test_cli_args_passing(self):
        script_content = """
import sys
if len(sys.argv) > 1 and sys.argv[1] == 'foobar':
    print("yes")
else:
    print("no")
"""
        script_path = self.create_file("args.py", script_content)
        cov = MiniCoverage(project_root=self.test_dir)

        with self.capture_stdout():
            cov.run(script_path, script_args=['foobar'])

        results = cov.analyze()
        stmt = results[script_path]['Statement']
        # Should hit line 4 (print yes) and miss line 6 (print no)
        self.assertIn(4, stmt['executed'])
        self.assertIn(6, stmt['missing'])