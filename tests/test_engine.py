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
        # Default context is 0
        self.assertIn(10, self.cov.trace_data['lines'][filename][0])

    def test_trace_function_arc_capture_same_file(self):
        filename = os.path.join(self.test_dir, "test.py")
        f1 = MockFrame(filename, 10)
        self.cov.trace_function(f1, "line", None)
        f2 = MockFrame(filename, 11)
        self.cov.trace_function(f2, "line", None)
        self.assertIn((10, 11), self.cov.trace_data['arcs'][filename][0])

    def test_dynamic_context_switching(self):
        filename = os.path.join(self.test_dir, "ctx.py")

        # 1. Trace in 'default'
        self.cov.trace_function(MockFrame(filename, 1), "line", None)

        # 2. Switch Context
        self.cov.switch_context("test_case_A")
        self.cov.trace_function(MockFrame(filename, 2), "line", None)

        # 3. Switch Again
        self.cov.switch_context("test_case_B")
        self.cov.trace_function(MockFrame(filename, 3), "line", None)

        # Verify in-memory structure
        lines = self.cov.trace_data['lines'][filename]
        # Context 0 (default) -> {1}
        self.assertIn(1, lines[0])

        # Get IDs for A and B
        id_a = self.cov.context_cache["test_case_A"]
        id_b = self.cov.context_cache["test_case_B"]

        self.assertIn(2, lines[id_a])
        self.assertIn(3, lines[id_b])

        # Save to DB and Verify persistence
        self.cov.save_data()

        # Inspect DB
        files = [f for f in os.listdir(self.test_dir) if ".coverage.db" in f]
        db_path = os.path.join(self.test_dir, files[0])
        conn = sqlite3.connect(db_path)
        cur = conn.cursor()

        # Check contexts table
        cur.execute("SELECT label FROM contexts WHERE label != 'default'")
        labels = {row[0] for row in cur.fetchall()}
        self.assertEqual(labels, {"test_case_A", "test_case_B"})

        # Check lines table has correct context mapping
        # Join lines with contexts to verify
        cur.execute("""
                    SELECT c.label, l.line_no
                    FROM lines l
                             JOIN contexts c ON l.context_id = c.id
                    WHERE l.file_path = ?
                    """, (filename,))
        rows = cur.fetchall()
        conn.close()

        self.assertIn(('default', 1), rows)
        self.assertIn(('test_case_A', 2), rows)
        self.assertIn(('test_case_B', 3), rows)

    def test_save_data_sqlite(self):
        filename = os.path.join(self.test_dir, "test.py")
        self.cov.trace_data['lines'][filename][0].add(1)

        self.cov.save_data()

        files = [f for f in os.listdir(self.test_dir) if ".coverage.db" in f]
        self.assertEqual(len(files), 1)

        db_path = os.path.join(self.test_dir, files[0])
        conn = sqlite3.connect(db_path)
        cur = conn.cursor()
        cur.execute("SELECT * FROM lines")
        rows = cur.fetchall()
        conn.close()

        self.assertEqual(len(rows), 1)
        # Schema: file, context_id, line
        self.assertEqual(rows[0][0], filename)
        self.assertEqual(rows[0][2], 1)

    def test_combine_data_sqlite(self):
        # Manually create a partial sqlite DB
        partial_name = f".coverage.db.{os.getpid()}.{uuid.uuid4().hex}"
        db_path = os.path.join(self.test_dir, partial_name)
        conn = sqlite3.connect(db_path)
        conn.execute("CREATE TABLE contexts (id INTEGER PRIMARY KEY, label TEXT)")
        conn.execute("INSERT INTO contexts VALUES (0, 'default'), (99, 'remote_ctx')")
        conn.execute("CREATE TABLE lines (file_path TEXT, context_id INTEGER, line_no INTEGER)")
        conn.execute("CREATE TABLE arcs (file_path TEXT, context_id INTEGER, start_line INTEGER, end_line INTEGER)")

        conn.execute("INSERT INTO lines VALUES (?, ?, ?)", ("f1.py", 99, 100))
        conn.commit()
        conn.close()

        self.cov.combine_data()

        main_db = os.path.join(self.test_dir, ".coverage.db")
        self.assertTrue(os.path.exists(main_db))

        conn = sqlite3.connect(main_db)
        cur = conn.cursor()

        # Verify context merge
        cur.execute("SELECT id FROM contexts WHERE label='remote_ctx'")
        res = cur.fetchone()
        self.assertIsNotNone(res)
        new_ctx_id = res[0]

        # Verify line merge re-mapped to new ID
        cur.execute("SELECT line_no FROM lines WHERE file_path='f1.py' AND context_id=?", (new_ctx_id,))
        res_line = cur.fetchone()
        conn.close()

        self.assertEqual(res_line[0], 100)
        self.assertFalse(os.path.exists(db_path))

    def test_config_data_file(self):
        self.cov.config['data_file'] = "custom.sqlite"
        filename = os.path.join(self.test_dir, "test.py")
        self.cov.trace_data['lines'][filename][0].add(1)

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

        # Access default context 0
        arcs = self.cov.trace_data['arcs'][filename][0]
        self.assertIn((10, 11), arcs)
        self.assertIn((20, 21), arcs)
        self.assertNotIn((10, 20), arcs)