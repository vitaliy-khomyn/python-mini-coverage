import unittest  # noqa: F401
import sys  # noqa: F401
import os
from src.engine import MiniCoverage
from tests.test_utils import BaseTestCase


class TestIntegration(BaseTestCase):

    def test_full_pipeline(self):
        script = """
def foo(x):
    if x: return 1
    return 0
if __name__ == "__main__":
    foo(True)
"""
        script_path = self.create_file("target.py", script)

        cov = MiniCoverage(project_root=self.test_dir)
        with self.capture_stdout():
            cov.run(script_path)

        results = cov.analyze()
        norm_path = os.path.normcase(os.path.realpath(script_path))
        stmt = results[norm_path]['Statement']
        self.assertGreater(len(stmt['executed']), 0)

        cov.report()
        self.assertTrue(os.path.exists(os.path.join(self.test_dir, "coverage.xml")))

    def test_threading_support(self):
        script = """
import threading
def worker():
    x = 1 + 1
t = threading.Thread(target=worker)
t.start()
t.join()
"""
        script_path = self.create_file("threaded.py", script)
        cov = MiniCoverage(project_root=self.test_dir)
        with self.capture_stdout():
            cov.run(script_path)

        results = cov.analyze()
        norm_path = os.path.normcase(os.path.realpath(script_path))
        stmt = results[norm_path]['Statement']
        self.assertTrue(any(line == 4 for line in stmt['executed']))

    def test_configuration_exclusion(self):
        script = """
def normal():
    return 1
def debug_info():
    return "debug"
"""
        script_path = self.create_file("exclude.py", script)

        # explicit newline formatting for configparser
        config = "[report]\nexclude_lines =\n    def debug_info"
        self.create_file(".coveragerc", config)

        cov = MiniCoverage(project_root=self.test_dir)
        with self.capture_stdout():
            cov.run(script_path)

        results = cov.analyze()
        norm_path = os.path.normcase(os.path.realpath(script_path))
        file_res = results[norm_path]['Statement']

        # line 4 (def debug_info) should be removed from possible lines
        self.assertNotIn(4, file_res['possible'])

    def test_cli_args_passing(self):
        script = """
import sys
if len(sys.argv) > 1 and sys.argv[1] == 'foo':
    print('yes')
"""
        script_path = self.create_file("args.py", script)
        cov = MiniCoverage(project_root=self.test_dir)
        with self.capture_stdout():
            cov.run(script_path, script_args=['foo'])

        results = cov.analyze()
        norm_path = os.path.normcase(os.path.realpath(script_path))
        self.assertIn(4, results[norm_path]['Statement']['executed'])
