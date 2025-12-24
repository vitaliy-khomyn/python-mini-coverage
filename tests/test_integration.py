import unittest
import os
import json
import sys
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
        stmt = results[script_path]['Statement']
        self.assertGreater(len(stmt['executed']), 0)

        cov.report()
        self.assertTrue(os.path.exists(os.path.join(self.test_dir, "coverage.xml")))
        self.assertTrue(os.path.exists(os.path.join(self.test_dir, "coverage.json")))

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
        stmt = results[script_path]['Statement']
        # Line 4 (x=1+1) must be executed
        self.assertTrue(any(line == 4 for line in stmt['executed']))

    def test_configuration_exclusion(self):
        script = """
def normal():
    return 1
def debug_info():
    return "debug"
"""
        script_path = self.create_file("exclude.py", script)
        self.create_file(".coveragerc", "[report]\nexclude_lines = def debug_info")

        cov = MiniCoverage(project_root=self.test_dir)
        with self.capture_stdout():
            cov.run(script_path)

        results = cov.analyze()
        file_res = results[script_path]['Statement']
        # Line 4 (def debug_info) should be removed from possible lines
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
        # Line 4 (print yes) should be hit
        self.assertIn(4, results[script_path]['Statement']['executed'])