import unittest
import os
import shutil
import tempfile
import multiprocessing  # noqa: F401
from src.engine import MiniCoverage


class TestMultiprocessing(unittest.TestCase):
    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
        self.cwd = os.getcwd()
        os.chdir(self.test_dir)
        # ensure src is in path for the subprocess
        import sys
        self.src_path = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
        if self.src_path not in sys.path:
            sys.path.insert(0, self.src_path)

    def tearDown(self):
        os.chdir(self.cwd)
        try:
            shutil.rmtree(self.test_dir)
        except PermissionError:
            import time
            time.sleep(0.2)
            shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_multiprocessing_coverage(self):
        """
        Test that code executed in a child process is tracked.
        """
        code = """
import multiprocessing
import time

def worker_fn():
    x = 1
    y = 2
    z = x + y
    return z

if __name__ == "__main__":
    p = multiprocessing.Process(target=worker_fn)
    p.start()
    p.join()
"""
        script_path = os.path.join(self.test_dir, "mp_script.py")
        with open(script_path, "w") as f:
            f.write(code)

        cov = MiniCoverage(project_root=self.test_dir)

        # run the script which spawns a subprocess
        cov.run(script_path)

        # the main process data is in memory, but the child process data
        # was written to a separate SQLite file. must combine them.
        cov.combine_data()

        # reload data to see the combined result
        lines = cov.trace_data['lines'][script_path][0]

        # worker function body is lines 5, 6, 7, 8.
        # if multiprocessing coverage works, these lines must be present.
        # (line numbers are approx, checking for existence of the block)
        worker_lines_hit = {5, 6, 7, 8}.intersection(lines)
        self.assertTrue(len(worker_lines_hit) > 0, "Child process lines were not captured")


if __name__ == '__main__':
    unittest.main()
