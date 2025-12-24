import unittest
import sys
import os
import threading
import sqlite3
import uuid
from contextlib import closing
from src.engine import MiniCoverage
from tests.test_utils import BaseTestCase, MockFrame


class TestEngineCore(BaseTestCase):

    def setUp(self):
        super().setUp()
        self.cov = MiniCoverage(project_root=self.test_dir)

    def test_initialization(self):
        self.assertEqual(self.cov.current_context, "default")
        self.assertIsNotNone(self.cov.config)

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

    def test_trace_function_arc_cross_file_reset(self):
        f1 = os.path.join(self.test_dir, "a.py")
        f2 = os.path.join(self.test_dir, "b.py")

        self.cov.trace_function(MockFrame(f1, 1), "line", None)
        self.cov.trace_function(MockFrame(f2, 1), "line", None)

        self.assertEqual(len(self.cov.trace_data['arcs'][f1][0]), 0)

        self.cov.trace_function(MockFrame(f2, 2), "line", None)
        self.assertIn((1, 2), self.cov.trace_data['arcs'][f2][0])

    def test_context_switching(self):
        self.cov.switch_context("ctx1")
        self.assertEqual(self.cov.current_context, "ctx1")
        cid1 = self.cov._get_current_context_id()
        self.assertGreater(cid1, 0)

        self.cov.switch_context("ctx2")
        cid2 = self.cov._get_current_context_id()
        self.assertNotEqual(cid1, cid2)

        self.cov.switch_context("ctx1")
        cid3 = self.cov._get_current_context_id()
        self.assertEqual(cid1, cid3)

    def test_trace_with_context_persistence(self):
        filename = os.path.join(self.test_dir, "test.py")

        self.cov.switch_context("test_A")
        self.cov.trace_function(MockFrame(filename, 10), "line", None)

        self.cov.save_data()

        files = [f for f in os.listdir(self.test_dir) if ".coverage.db" in f]
        self.assertEqual(len(files), 1)
        db_path = os.path.join(self.test_dir, files[0])

        # Use context manager to ensure close
        with closing(sqlite3.connect(db_path)) as conn:
            cur = conn.cursor()
            cur.execute("SELECT id, label FROM contexts")
            ctx_map = {label: cid for cid, label in cur.fetchall()}
            self.assertIn("test_A", ctx_map)

            cur.execute("SELECT context_id, line_no FROM lines")
            lines = cur.fetchall()
            self.assertIn((ctx_map["test_A"], 10), lines)

    def test_context_thread_safety(self):
        def worker(idx):
            for _ in range(50):
                self.cov.switch_context(f"thread_{idx}")

        threads = [threading.Thread(target=worker, args=(i,)) for i in range(5)]
        for t in threads: t.start()
        for t in threads: t.join()

        self.assertEqual(len(self.cov.context_cache), 6)

    def test_save_data_sqlite(self):
        filename = os.path.join(self.test_dir, "test.py")
        self.cov.trace_data['lines'][filename][0].add(1)

        self.cov.save_data()

        files = [f for f in os.listdir(self.test_dir) if ".coverage.db" in f]
        self.assertEqual(len(files), 1)

        db_path = os.path.join(self.test_dir, files[0])
        with closing(sqlite3.connect(db_path)) as conn:
            cur = conn.cursor()
            cur.execute("PRAGMA foreign_key_check")
            errors = cur.fetchall()
            self.assertEqual(len(errors), 0, "Foreign key errors found")

            cur.execute("SELECT * FROM lines")
            rows = cur.fetchall()
            self.assertEqual(len(rows), 1)

    def test_combine_data_sqlite(self):
        main_db = os.path.join(self.test_dir, ".coverage.db")
        # Ensure unique partial name to avoid glob mismatch
        partial_db = f"{main_db}.123.{uuid.uuid4().hex}"

        with closing(sqlite3.connect(partial_db)) as conn:
            conn.execute("CREATE TABLE contexts (id INTEGER PRIMARY KEY, label TEXT)")
            conn.execute("INSERT INTO contexts VALUES (99, 'remote')")
            conn.execute("CREATE TABLE lines (file_path TEXT, context_id INTEGER, line_no INTEGER)")
            conn.execute("INSERT INTO lines VALUES ('remote.py', 99, 100)")
            conn.execute("CREATE TABLE arcs (file_path TEXT, context_id INTEGER, start_line INTEGER, end_line INTEGER)")
            conn.commit()

        self.cov.combine_data()

        with closing(sqlite3.connect(main_db)) as conn:
            cur = conn.cursor()
            cur.execute("SELECT id FROM contexts WHERE label='remote'")
            res = cur.fetchone()
            self.assertIsNotNone(res)
            new_ctx_id = res[0]

            cur.execute("SELECT line_no FROM lines WHERE context_id=?", (new_ctx_id,))
            self.assertEqual(cur.fetchone()[0], 100)

        self.assertFalse(os.path.exists(partial_db))

    def test_combine_duplicate_contexts(self):
        main_db = os.path.join(self.test_dir, ".coverage.db")

        p1 = f"{main_db}.1.a"
        with closing(sqlite3.connect(p1)) as c1:
            c1.execute("CREATE TABLE contexts (id, label)")
            c1.execute("INSERT INTO contexts VALUES (10, 'common')")
            c1.execute("CREATE TABLE lines (file_path, context_id, line_no)")
            c1.execute("CREATE TABLE arcs (file_path, context_id, start_line, end_line)")
            c1.commit()

        p2 = f"{main_db}.2.b"
        with closing(sqlite3.connect(p2)) as c2:
            c2.execute("CREATE TABLE contexts (id, label)")
            c2.execute("INSERT INTO contexts VALUES (20, 'common')")
            c2.execute("CREATE TABLE lines (file_path, context_id, line_no)")
            c2.execute("CREATE TABLE arcs (file_path, context_id, start_line, end_line)")
            c2.commit()

        self.cov.combine_data()

        with closing(sqlite3.connect(main_db)) as conn:
            cur = conn.cursor()
            cur.execute("SELECT count(*) FROM contexts WHERE label='common'")
            count = cur.fetchone()[0]
            self.assertEqual(count, 1, "Should merge duplicate context labels")

    def test_config_data_file_custom(self):
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

        arcs = self.cov.trace_data['arcs'][filename][0]
        self.assertIn((10, 11), arcs)
        self.assertIn((20, 21), arcs)
        self.assertNotIn((10, 20), arcs)