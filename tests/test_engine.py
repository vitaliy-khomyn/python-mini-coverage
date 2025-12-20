import unittest
import sys
import os
import threading
import sqlite3
import uuid
from src.engine import MiniCoverage
from tests.test_utils import BaseTestCase, MockFrame


class TestEngineCore(BaseTestCase):

    def setUp(self):
        super().setUp()
        self.cov = MiniCoverage(project_root=self.test_dir)

    def test_should_trace_filters(self):
        in_project = os.path.join(self.test_dir, "script.py")
        self.assertTrue(self.cov._should_trace(in_project))

        outside = "/tmp/other.py"
        self.assertFalse(self.cov._should_trace(outside))

        self.assertFalse(self.cov._should_trace(__file__))

    def test_trace_function_line_capture(self):
        filename = os.path.join(self.test_dir, "test.py")
        frame = MockFrame(filename, 10)
        self.cov.trace_function(frame, "line", None)
        self.assertIn(10, self.cov.trace_data['lines'][filename])

    def test_trace_function_arc_capture_same_file(self):
        filename = os.path.join(self.test_dir, "test.py")
        f1 = MockFrame(filename, 10)
        self.cov.trace_function(f1, "line", None)
        f2 = MockFrame(filename, 11)
        self.cov.trace_function(f2, "line", None)
        self.assertIn((10, 11), self.cov.trace_data['arcs'][filename])

    def test_save_data_sqlite(self):
        filename = os.path.join(self.test_dir, "test.py")
        self.cov.trace_data['lines'][filename].add(1)

        self.cov.save_data()

        # Should create a partial DB file
        files = [f for f in os.listdir(self.test_dir) if ".coverage.db" in f]
        self.assertEqual(len(files), 1)

        # Verify content with sqlite3
        db_path = os.path.join(self.test_dir, files[0])
        conn = sqlite3.connect(db_path)
        cur = conn.cursor()
        cur.execute("SELECT * FROM lines")
        rows = cur.fetchall()
        conn.close()

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0][0], filename)
        self.assertEqual(rows[0][1], 1)

    def test_combine_data_sqlite(self):
        # Manually create a partial sqlite DB
        partial_name = f".coverage.db.{os.getpid()}.{uuid.uuid4().hex}"
        db_path = os.path.join(self.test_dir, partial_name)
        conn = sqlite3.connect(db_path)
        conn.execute("CREATE TABLE lines (file_path TEXT, line_no INTEGER)")
        conn.execute("CREATE TABLE arcs (file_path TEXT, start_line INTEGER, end_line INTEGER)")
        conn.execute("INSERT INTO lines VALUES (?, ?)", ("f1.py", 1))
        conn.commit()
        conn.close()

        # Ensure we are using default config data file
        self.cov.combine_data()

        # Verify Main DB
        main_db = os.path.join(self.test_dir, ".coverage.db")
        self.assertTrue(os.path.exists(main_db))

        conn = sqlite3.connect(main_db)
        cur = conn.cursor()
        cur.execute("SELECT line_no FROM lines WHERE file_path='f1.py'")
        result = cur.fetchone()
        conn.close()

        self.assertEqual(result[0], 1)
        # Partial file should be deleted
        self.assertFalse(os.path.exists(db_path))

    def test_config_data_file(self):
        # Test saving to a custom DB name
        self.cov.config['data_file'] = "custom.sqlite"
        filename = os.path.join(self.test_dir, "test.py")
        self.cov.trace_data['lines'][filename].add(1)

        self.cov.save_data()

        files = [f for f in os.listdir(self.test_dir) if "custom.sqlite" in f]
        self.assertEqual(len(files), 1)

    def test_thread_local_storage(self):
        filename = os.path.join(self.test_dir, "threaded.py")

        def t1_work():
            f1 = MockFrame(filename, 10)
            self.cov.trace_function(f1, "line", None)
            import time;
            time.sleep(0.01)
            f2 = MockFrame(filename, 11)
            self.cov.trace_function(f2, "line", None)

        def t2_work():
            f1 = MockFrame(filename, 20)
            self.cov.trace_function(f1, "line", None)
            f2 = MockFrame(filename, 21)
            self.cov.trace_function(f2, "line", None)

        th1 = threading.Thread(target=t1_work)
        th2 = threading.Thread(target=t2_work)
        th1.start();
        th2.start()
        th1.join();
        th2.join()

        arcs = self.cov.trace_data['arcs'][filename]
        self.assertIn((10, 11), arcs)
        self.assertIn((20, 21), arcs)
        self.assertNotIn((10, 20), arcs)