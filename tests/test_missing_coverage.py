import unittest
import sys
import os
import sqlite3
import time  # noqa: F401
from unittest.mock import MagicMock, patch, ANY  # noqa: F401
from src.engine import MiniCoverage
from src.engine.storage import CoverageStorage  # noqa: F401


class TestMissingCoverage(unittest.TestCase):
    def setUp(self):
        self.cov = MiniCoverage()

    def test_start_sys_monitoring_failure_fallback(self):
        """Test that if sys.monitoring fails, we fallback to sys.settrace."""
        if sys.version_info < (3, 12):
            self.skipTest("sys.monitoring only available in 3.12+")

        # mock sys.monitoring.use_tool_id to raise ValueError (simulating failure)
        with patch('sys.monitoring.use_tool_id', side_effect=ValueError("Mock Failure")):
            with patch('sys.settrace') as mock_settrace:
                self.cov.start()
                # should have tried to settrace as fallback
                mock_settrace.assert_called()
        self.cov.stop()

    def test_stop_sys_monitoring_exception(self):
        """Test that exceptions during stop_sys_monitoring are caught."""
        if sys.version_info < (3, 12):
            self.skipTest("sys.monitoring only available in 3.12+")

        with patch('sys.monitoring.set_events', side_effect=ValueError("Stop Error")):
            # should not raise exception
            self.cov.sys_monitoring_tracer.stop()

    def test_storage_save_exception(self):
        """Test that save handles DB exceptions gracefully."""
        # add some dummy data so save() proceeds
        self.cov.trace_data['lines']['dummy.py'][0].add(1)

        with patch('sqlite3.connect', side_effect=Exception("DB Error")):
            with self.assertLogs('src.engine.storage', level='ERROR') as cm:
                self.cov.storage.save(self.cov.trace_data, self.cov.context_cache)
                self.assertTrue(any("Failed to save coverage data" in o for o in cm.output))

    def test_storage_combine_operational_error(self):
        """Test that combine handles locked files (OperationalError)."""
        with patch('glob.glob', return_value=['partial.db']):
            with patch('sqlite3.connect') as mock_connect:
                mock_conn = MagicMock()
                mock_connect.return_value = mock_conn

                # only fail on ATTACH, succeed on INIT queries
                def side_effect(query, *args):
                    if "ATTACH DATABASE" in query:
                        raise sqlite3.OperationalError("Locked")
                    return MagicMock()
                mock_conn.cursor.return_value.execute.side_effect = side_effect

                with self.assertLogs('src.engine.storage', level='DEBUG') as cm:
                    self.cov.storage.combine(lambda x: x)
                    self.assertTrue(any("Skipping locked/corrupt" in o for o in cm.output))

    def test_storage_combine_generic_error(self):
        """Test that combine handles generic exceptions."""
        with patch('glob.glob', return_value=['partial.db']):
            with patch('sqlite3.connect', side_effect=Exception("Boom")):
                with self.assertLogs('src.engine.storage', level='ERROR') as cm:
                    self.cov.storage.combine(lambda x: x)
                    self.assertTrue(any("Error combining" in o for o in cm.output))

    def test_storage_combine_os_remove_retry(self):
        """Test the retry logic when deleting partial files."""
        with patch('glob.glob', return_value=['partial.db']):
            with patch('sqlite3.connect'):
                # 1. fail twice with OSError, then succeed (return None)
                with patch('os.remove', side_effect=[OSError("Busy"), OSError("Busy"), None]) as mock_remove:
                    with patch('time.sleep') as mock_sleep:
                        self.cov.storage.combine(lambda x: x)
                        self.assertEqual(mock_remove.call_count, 3)
                        self.assertEqual(mock_sleep.call_count, 2)

    def test_load_into_missing_file(self):
        """Test load_into with non-existent file."""
        self.cov.storage.data_file = "non_existent.db"
        # should not raise
        self.cov.storage.load_into(self.cov.trace_data, self.cov.path_manager)

    def test_load_into_operational_error(self):
        """Test load_into with corrupt DB."""
        with patch('os.path.exists', return_value=True):
            with patch('sqlite3.connect', side_effect=sqlite3.OperationalError("Corrupt")):
                with self.assertLogs('src.engine.storage', level='DEBUG') as cm:
                    self.cov.storage.load_into(self.cov.trace_data, self.cov.path_manager)
                    self.assertTrue(any("OperationalError loading" in o for o in cm.output))

    def test_patch_multiprocessing_idempotency(self):
        """Test that _patch_multiprocessing can be called multiple times."""
        self.cov._patch_multiprocessing()
        # mock the patched flag
        import multiprocessing
        self.assertTrue(hasattr(multiprocessing, '_mini_coverage_patched'))

        # call again
        self.cov._patch_multiprocessing()
        # should still be patched and not crash
        self.assertTrue(hasattr(multiprocessing, '_mini_coverage_patched'))

    def test_run_re_raises_exceptions(self):
        """Test that run() re-raises exceptions from the script."""
        with patch('builtins.open', unittest.mock.mock_open(read_data="raise ValueError('Test')")):
            with self.assertRaises(ValueError):
                self.cov.run("dummy_script.py")

    def test_run_re_raises_system_exit(self):
        """Test that run() re-raises SystemExit."""
        with patch('builtins.open', unittest.mock.mock_open(read_data="import sys; sys.exit(1)")):
            with self.assertRaises(SystemExit):
                self.cov.run("dummy_script.py")

    def test_should_trace_exclusions(self):
        """Test _should_trace logic for exclusions."""
        # setup config with omit pattern
        self.cov.config.omit = ['vendor/*']

        # test excluded file
        excluded_path = os.path.normcase(os.path.join(self.cov.project_root, "excluded.py"))
        self.cov.excluded_files.add(excluded_path)
        self.assertFalse(self.cov.path_manager.should_trace(excluded_path, self.cov.excluded_files))

        # test omit pattern
        vendor_path = os.path.join(self.cov.project_root, "vendor/lib.py")
        self.assertFalse(self.cov.path_manager.should_trace(vendor_path, self.cov.excluded_files))

        # test outside project root
        self.assertFalse(self.cov.path_manager.should_trace("/tmp/outside.py", self.cov.excluded_files))

        # test valid file
        valid_path = os.path.join(self.cov.project_root, "valid.py")
        self.assertTrue(self.cov.path_manager.should_trace(valid_path, self.cov.excluded_files))
