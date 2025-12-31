from typing import Generator, Optional
import unittest
import os
import shutil
import tempfile
import sys
from contextlib import contextmanager
import io


class BaseTestCase(unittest.TestCase):
    """
    Base class for tests that need temporary files or directories.
    """
    def setUp(self) -> None:
        self.test_dir = tempfile.mkdtemp()
        self.old_cwd = os.getcwd()
        os.chdir(self.test_dir)

    def tearDown(self) -> None:
        os.chdir(self.old_cwd)
        # Fix: ignore_errors=True to prevent Windows file lock crashes
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def create_file(self, filename, content) -> str:
        """
        Helper to create a file with given content in the test dir.
        Returns absolute path.
        """
        filepath = os.path.join(self.test_dir, filename)
        os.makedirs(os.path.dirname(filepath), exist_ok=True)
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(content)
        return filepath

    @contextmanager
    def capture_stdout(self) -> Generator[Optional[io.StringIO]]:
        """
        Captures stdout for testing console output.
        """
        new_out = io.StringIO()
        old_out = sys.stdout
        try:
            sys.stdout = new_out
            yield new_out
        finally:
            sys.stdout = old_out


class MockFrame:
    """
    Simulates a Python stack frame for testing trace functions manually.
    """
    def __init__(self, filename, lineno, code_name="<module>"):
        self.f_lineno = lineno
        self.f_code = MockCode(filename, code_name)
        # Added for Bytecode/MC/DC support
        self.f_lasti = 0
        self.f_trace_opcodes = False


class MockCode:
    def __init__(self, filename, name):
        self.co_filename = filename
        self.co_name = name
