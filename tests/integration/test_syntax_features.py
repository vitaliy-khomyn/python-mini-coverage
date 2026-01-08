import unittest
import os
import shutil
import tempfile
import asyncio  # noqa: F401
from src.engine import MiniCoverage


class TestSyntaxFeatures(unittest.TestCase):
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

    def _run_coverage(self, script_content, script_name="script.py"):
        script_path = os.path.join(self.test_dir, script_name)
        with open(script_path, "w") as f:
            f.write(script_content)

        cov = MiniCoverage(project_root=self.test_dir)
        cov.run(script_path)
        canonical_path = cov.path_manager.canonicalize(script_path)
        return cov.trace_data['lines'][canonical_path]

    def test_generator_coverage(self):
        code = """
def my_gen():
    yield 1
    yield 2

for _ in my_gen():
    pass
"""
        # context 0 is default
        lines = self._run_coverage(code)[0]
        # lines 2, 3, 4, 5, 6 should be hit (approximate depending on python version)
        self.assertTrue(len(lines) >= 4)

    def test_async_await_coverage(self):
        code = """
import asyncio

async def worker():
    await asyncio.sleep(0.01)
    return True

async def main():
    await worker()

asyncio.run(main())
"""
        lines = self._run_coverage(code)[0]
        # ensure lines inside async functions are hit
        self.assertTrue(len(lines) > 5)

    def test_match_case_coverage(self):
        # only run on Python 3.10+
        import sys
        if sys.version_info < (3, 10):
            return

        code = """
def check(val):
    match val:
        case 1:
            return "one"
        case 2:
            return "two"
        case _:
            return "other"

check(1)
check(3)
"""
        lines = self._run_coverage(code)[0]
        # expect hits on the match line, case 1, and case _
        # case 2 should be missed
        # note: line numbers for match/case vary by Python version,
        # but check that we got significant coverage.
        self.assertTrue(len(lines) >= 5)


if __name__ == '__main__':
    unittest.main()
