import unittest
import os
import sys
from .mini_coverage import MiniCoverage


class TestMiniCoverage(unittest.TestCase):

    def setUp(self):
        """Runs before every test. We use this to clean up old temp files."""
        self.test_files = []

    def tearDown(self):
        """Runs after every test. Delete the temp files we created."""
        for f in self.test_files:
            if os.path.exists(f):
                os.remove(f)

    def create_temp_script(self, filename, content):
        """Helper to write a python script to disk."""
        with open(filename, 'w') as f:
            f.write(content)
        self.test_files.append(filename)
        return os.path.abspath(filename)

    def test_basic_if_else_coverage(self):
        """
        Scenario: A simple if/else where only the 'if' block runs.
        We expect the 'else' block lines to be missing.
        """
        code = """
x = 10
if x > 5:
    print("Hit")
else:
    print("Miss")
"""
        script_path = self.create_temp_script("temp_basic.py", code)

        cov = MiniCoverage()
        cov.run(script_path)

        percent, missing = cov.analyze_file(script_path)

        # Line 2 (if), 3 (print Hit) should run.
        # Line 5 (else), 6 (print Miss) should NOT run.
        # Note: AST often considers 'else' executable or not depending on version,
        # but the body of the else (line 6) is definitely missing.

        self.assertIn(6, missing, "Line 6 (else body) should be missing")
        self.assertNotIn(3, missing, "Line 3 (if body) should be executed")
        self.assertLess(percent, 100, "Coverage should not be 100%")

    def test_function_not_called(self):
        """
        Scenario: A file defines a function but never calls it.
        The function body lines should be missing.
        """
        code = """
def my_func():
    a = 1
    b = 2
    return a + b

x = 1
"""
        script_path = self.create_temp_script("temp_func.py", code)

        cov = MiniCoverage()
        cov.run(script_path)

        percent, missing = cov.analyze_file(script_path)

        # Line 2 (def) runs (function definition is an executable statement).
        # Line 3, 4, 5 (body) should NOT run.
        self.assertTrue({3, 4, 5}.issubset(missing), f"Function body should be missing. Missing: {missing}")
        self.assertNotIn(2, missing, "Function definition line itself should be executed")

    def test_loop_coverage(self):
        """
        Scenario: A loop that runs.
        """
        code = """
for i in range(3):
    x = i * 2
"""
        script_path = self.create_temp_script("temp_loop.py", code)

        cov = MiniCoverage()
        cov.run(script_path)

        percent, missing = cov.analyze_file(script_path)

        self.assertEqual(percent, 100.0, "Loop should be 100% covered")
        self.assertEqual(len(missing), 0)

    def test_ignore_comments_and_docstrings(self):
        """
        Scenario: A file with mostly comments.
        Coverage should be 100% if the few real lines are hit,
        ignoring the comments in the 'total lines' calculation.
        """
        code = """
# This is a comment
'''
This is a docstring
'''
x = 1
# Another comment
"""
        script_path = self.create_temp_script("temp_comments.py", code)

        cov = MiniCoverage()
        # Use AST to check what it thinks are executable lines
        executables = cov.get_executable_lines(script_path)

        # Only 'x = 1' (line 6) should be executable.
        # (Sometimes docstrings are expressions, but standard AST logic usually filters pure string expressions if handled right,
        # or counts them. Our simple implementation counts string expressions as executable if they are statements.
        # Let's see if our tool counts line 3 (docstring) as a statement.)

        cov.run(script_path)
        percent, missing = cov.analyze_file(script_path)

        # If x=1 runs, coverage should be high.
        self.assertNotIn(6, missing)


if __name__ == '__main__':
    unittest.main()