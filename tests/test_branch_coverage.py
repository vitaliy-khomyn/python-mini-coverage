import unittest
import os
import sys
import types
import ast
from unittest.mock import MagicMock, patch
from src.engine import MiniCoverage
from src.config_loader import ConfigLoader
from src.source_parser import SourceParser


class TestBranchCoverage(unittest.TestCase):
    def setUp(self):
        self.cov = MiniCoverage()

    def test_map_path_logic(self):
        """Test _map_path with configured aliases."""
        # Setup config with paths
        # We use normcase to ensure the test works on both Windows and Linux
        src_alias = os.path.normcase("/w/source/")
        src_canonical = os.path.normcase("/src/")

        self.cov.config['paths'] = {
            src_canonical: [src_alias]
        }

        # Mock os.path.exists to return False so realpath doesn't interfere
        with patch('os.path.exists', return_value=False):
            # Case 1: Match found
            input_path = os.path.join(src_alias, "file.py")
            mapped = self.cov._map_path(input_path)

            expected = os.path.join(src_canonical, "file.py")
            self.assertEqual(mapped, expected)

            # Case 2: No match
            nomatch_path = os.path.normcase("/nomatch/file.py")
            mapped = self.cov._map_path(nomatch_path)
            self.assertEqual(mapped, nomatch_path)

    def test_monitor_py_start_negative(self):
        """Test _monitor_py_start when file should NOT be traced."""
        if sys.version_info < (3, 12):
            self.skipTest("sys.monitoring only in 3.12+")

        # Safety: ensure sys.monitoring is disabled to prevent infinite recursion
        # if a previous test leaked the tool ID.
        try:
            sys.monitoring.set_events(sys.monitoring.COVERAGE_ID, 0)
        except (AttributeError, Exception):
            pass

        code = MagicMock(spec=types.CodeType)
        code.co_filename = "excluded.py"

        with patch.object(self.cov, '_should_trace', return_value=False):
            with patch('sys.monitoring.set_local_events') as mock_set:
                self.cov._monitor_py_start(code, 0)
                # Should call set_local_events with 0 (disable)
                mock_set.assert_any_call(sys.monitoring.COVERAGE_ID, code, 0)

    def test_monitor_py_resume(self):
        """Test that _monitor_py_resume clears history."""
        self.cov.thread_local.last_line = 10
        self.cov.thread_local.last_lasti = 20

        code = MagicMock(spec=types.CodeType)
        self.cov._monitor_py_resume(code, 0)

        self.assertIsNone(self.cov.thread_local.last_line)
        self.assertIsNone(self.cov.thread_local.last_lasti)

    def test_trace_function_clears_history(self):
        """Test that trace_function clears history on call/return."""
        frame = MagicMock()
        frame.f_code.co_filename = "test.py"

        # Test 'call' event
        self.cov.thread_local.last_line = 10
        self.cov.thread_local.last_lasti = 20
        self.cov.trace_function(frame, "call", None)
        self.assertIsNone(self.cov.thread_local.last_line)
        self.assertIsNone(self.cov.thread_local.last_lasti)

        # Test 'return' event
        self.cov.thread_local.last_line = 10
        self.cov.trace_function(frame, "return", None)
        self.assertIsNone(self.cov.thread_local.last_line)

    def test_trace_function_other_events(self):
        """Test trace_function ignores other events."""
        frame = MagicMock()
        res = self.cov.trace_function(frame, "exception", None)
        self.assertEqual(res, self.cov.trace_function)

    def test_config_loader_parsing(self):
        """Test ConfigLoader parsing logic."""
        loader = ConfigLoader()

        # Test _parse_list with mixed separators
        raw = "a, b\nc,d"
        res = loader._parse_list(raw)
        self.assertEqual(res, {'a', 'b', 'c', 'd'})

        # Test _load_ini with alternative section names
        config = {'omit': set(), 'include': set(), 'source': set()}
        with open("dummy.ini", "w") as f:
            f.write("[coverage:run]\nomit = *.tmp")

        try:
            res = loader._load_ini("dummy.ini", config)
            self.assertTrue(res)
            self.assertIn("*.tmp", config['omit'])
        finally:
            if os.path.exists("dummy.ini"):
                os.remove("dummy.ini")

    def test_source_parser_regex_error(self):
        """Test SourceParser handles invalid regex patterns gracefully."""
        parser = SourceParser()
        with open("dummy.py", "w") as f:
            f.write("x = 1")

        try:
            patterns = ["(unclosed group"]
            with self.assertLogs('src.source_parser', level='DEBUG') as cm:
                parser.parse_source("dummy.py", exclude_patterns=patterns)
                self.assertTrue(any("Invalid regex pattern" in o for o in cm.output))
        finally:
            if os.path.exists("dummy.py"):
                os.remove("dummy.py")

    def test_analyze_aggregation(self):
        """Test that analyze aggregates data from multiple raw paths mapping to same file."""
        # Mock normcase to force collision
        with patch('os.path.normcase', side_effect=lambda p: p.lower()):
            with patch('os.path.realpath', side_effect=lambda p: p):
                with patch('os.path.exists', return_value=True):
                    f1 = "File.py"
                    f2 = "file.py"

                    self.cov.trace_data['lines'][f1][0].add(1)
                    self.cov.trace_data['lines'][f2][0].add(2)

                    # Mock dependencies
                    # Use real AST and Code Object to ensure metrics work and don't crash
                    real_ast = ast.parse("x=1\ny=2")
                    real_code = compile("x=1\ny=2", "file.py", "exec")

                    self.cov.parser.parse_source = MagicMock(return_value=(real_ast, set()))
                    self.cov.parser.compile_source = MagicMock(return_value=real_code)
                    self.cov._should_trace = MagicMock(return_value=True)

                    # Run analyze
                    results = self.cov.analyze()

                    # Check if lines were merged (1 and 2)
                    # The canonical filename chosen depends on set iteration order of raw files
                    self.assertEqual(len(results), 1)
                    result_key = list(results.keys())[0]
                    stmt_stats = results[result_key]["Statement"]
                    self.assertEqual(len(stmt_stats['executed']), 2)
