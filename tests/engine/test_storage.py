import unittest
import sqlite3
from unittest.mock import MagicMock, patch
from src.engine import MiniCoverage
from src.engine.trace_data import TraceDataType


class TestStorage(unittest.TestCase):
    def setUp(self):
        self.cov = MiniCoverage()

    def test_storage_save_exception(self):
        self.cov.trace_data[TraceDataType.LINES]['dummy.py'][0].add(1)
        with patch('sqlite3.connect', side_effect=Exception("DB Error")):
            with self.assertLogs('src.engine.storage', level='ERROR') as cm:
                self.cov.storage.save(self.cov.trace_data, self.cov.tracer_controller.context_cache)
                self.assertTrue(any("Failed to save coverage data" in o for o in cm.output))

    def test_storage_combine_operational_error(self):
        with patch('glob.glob', return_value=['partial.db']):
            with patch('sqlite3.connect') as mock_connect:
                mock_conn = MagicMock()
                mock_connect.return_value = mock_conn

                def side_effect(query, *args):
                    if "ATTACH DATABASE" in query:
                        raise sqlite3.OperationalError("Locked")
                    return MagicMock()
                mock_conn.cursor.return_value.execute.side_effect = side_effect

                with self.assertLogs('src.engine.storage', level='DEBUG') as cm:
                    self.cov.storage.combine(lambda x: x)
                    self.assertTrue(any("Skipping locked/corrupt" in o for o in cm.output))

    def test_storage_combine_generic_error(self):
        with patch('glob.glob', return_value=['partial.db']):
            with patch('sqlite3.connect', side_effect=Exception("Boom")):
                with self.assertLogs('src.engine.storage', level='ERROR') as cm:
                    self.cov.storage.combine(lambda x: x)
                    self.assertTrue(any("Error merging" in o for o in cm.output))

    def test_storage_combine_os_remove_error(self):
        with patch('glob.glob', return_value=['partial.db']):
            with patch('sqlite3.connect'):
                with patch('os.remove', side_effect=OSError("Busy")) as mock_remove:
                    self.cov.storage.combine(lambda x: x)
                    self.assertEqual(mock_remove.call_count, 1)

    def test_load_into_missing_file(self):
        self.cov.storage.data_file = "non_existent.db"
        self.cov.storage.load_into(self.cov.trace_data, self.cov.path_manager)

    def test_load_into_operational_error(self):
        with patch('os.path.exists', return_value=True):
            with patch('sqlite3.connect', side_effect=sqlite3.OperationalError("Corrupt")):
                with self.assertLogs('src.engine.storage', level='DEBUG') as cm:
                    self.cov.storage.load_into(self.cov.trace_data, self.cov.path_manager)
                    self.assertTrue(any("OperationalError loading" in o for o in cm.output))
