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

    def test_initialization(self):
        self.assertEqual(self.cov.current_context, "default")
        self.assertIsNotNone(self.cov.config)
        self.assertEqual(self.cov.context_cache["default"], 0)

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

        # Should NOT link a.py:1 -> b.py:1
        self.assertEqual(len(self.cov.trace_data['arcs'][f1][0]), 0)

        self.cov.trace_function(MockFrame(f2, 2), "line", None)
        # Should link b.py:1 -> b.py:2
        self.assertIn((1, 2), self.cov.trace_data['arcs'][f2][0])

    # --- Dynamic Context Tests ---

    def test_context_switching(self):
        self.cov.switch_context("ctx1")
        self.assertEqual(self.cov.current_context, "ctx1")
        cid1 = self.cov._get_current_context_id()
        self.assertGreater(cid1, 0)

        self.cov.switch_context("ctx2")
        cid2 = self.cov._get_current_context_id()
        self.assertNotEqual(cid1, cid2)

        # Re-use existing ID
        self.cov.switch_context("ctx1")
        cid3 = self.cov._get_current_context_id()
        self.assertEqual(cid1, cid3)

    def test_trace_with_context(self):
        filename = os.path.join(self.test_dir, "test.py")

        self.cov.switch_context("test_A")
        self.cov.trace_function(MockFrame(filename, 10), "line", None)

        self.cov.switch_context("test_B")
        self.cov.trace_function(MockFrame(filename, 20), "line", None)

        # Verify persistence in DB
        self.cov.save_data()

        files = [f for f in os.listdir(self.test_dir) if ".coverage.db" in f]
        self.assertEqual(len(files), 1)
        db_path = os.path.join(self.test_dir, files[0])

        conn = sqlite3.connect(db_path)
        cur = conn.cursor()

        # Verify Contexts
        cur.execute("SELECT id, label FROM contexts")
        ctx_rows = cur.fetchall()
        ctx_map = {label: cid for cid, label in ctx_rows}
        self.assertIn("test_A", ctx_map)
        self.assertIn("test_B", ctx_map)

        # Verify Lines
        cur.execute("SELECT context_id, line_no FROM lines")
        lines = cur.fetchall()
        self.assertIn((ctx_map["test_A"], 10), lines)
        self.assertIn((ctx_map["test_B"], 20), lines)
        conn.close()

    def test_context_thread_safety(self):
        # Stress test context creation
        def worker(idx):
            for _ in range(50):
                self.cov.switch_context(f"thread_{idx}")

        threads = [threading.Thread(target=worker, args=(i,)) for i in range(5)]
        for t in threads: t.start()
        for t in threads: t.join()

        # Should have 5 new contexts + default
        self.assertEqual(len(self.cov.context_cache), 6)

    # --- DB & Persistence Tests ---

    def test_save_data_sqlite(self):
        filename = os.path.join(self.test_dir, "test.py")
        self.cov.trace_data['lines'][filename][0].add(1)

        self.cov.save_data()

        files = [f for f in os.listdir(self.test_dir) if ".coverage.db" in f]
        self.assertEqual(len(files), 1)

        db_path = os.path.join(self.test_dir, files[0])
        conn = sqlite3.connect(db_path)
        cur = conn.cursor()

        # Check integrity
        cur.execute("PRAGMA foreign_key_check")
        errors = cur.fetchall()
        self.assertEqual(len(errors), 0, "Foreign key errors found")

        cur.execute("SELECT * FROM lines")
        rows = cur.fetchall()
        self.assertEqual(len(rows), 1)
        conn.close()

    def test_combine_data_sqlite(self):
        # Create a partial DB manually
        main_db = os.path.join(self.test_dir, ".coverage.db")
        partial_db = main_db + ".partial"

        conn = sqlite3.connect(partial_db)
        conn.execute("CREATE TABLE contexts (id INTEGER PRIMARY KEY, label TEXT)")
        conn.execute("INSERT INTO contexts VALUES (99, 'remote')")
        conn.execute("CREATE TABLE lines (file_path TEXT, context_id INTEGER, line_no INTEGER)")
        conn.execute("INSERT INTO lines VALUES ('remote.py', 99, 100)")
        conn.execute("CREATE TABLE arcs (file_path TEXT, context_id INTEGER, start_line INTEGER, end_line INTEGER)")
        conn.commit()
        conn.close()

        # Run combine
        self.cov.combine_data()

        # Verify Main DB
        conn = sqlite3.connect(main_db)
        cur = conn.cursor()

        # Context should be merged
        cur.execute("SELECT id FROM contexts WHERE label='remote'")
        res = cur.fetchone()
        self.assertIsNotNone(res)
        new_ctx_id = res[0]
        self.assertNotEqual(new_ctx_id, 99)  # Should be remapped (likely 1 or 2)

        # Line should use new context ID
        cur.execute("SELECT line_no FROM lines WHERE context_id=?", (new_ctx_id,))
        self.assertEqual(cur.fetchone()[0], 100)
        conn.close()

        # Partial should be gone
        self.assertFalse(os.path.exists(partial_db))

    def test_combine_duplicate_contexts(self):
        # Ensure we don't duplicate labels when merging multiple files
        main_db = os.path.join(self.test_dir, ".coverage.db")

        # Partial 1: ctx='common'
        p1 = main_db + ".1"
        c1 = sqlite3.connect(p1)
        c1.execute("CREATE TABLE contexts (id, label)")
        c1.execute("INSERT INTO contexts VALUES (10, 'common')")
        c1.execute("CREATE TABLE lines (file_path, context_id, line_no)")
        c1.execute("CREATE TABLE arcs (file_path, context_id, start_line, end_line)")
        c1.commit();
        c1.close()

        # Partial 2: ctx='common'
        p2 = main_db + ".2"
        c2 = sqlite3.connect(p2)
        c2.execute("CREATE TABLE contexts (id, label)")
        c2.execute("INSERT INTO contexts VALUES (20, 'common')")  # Different local ID
        c2.execute("CREATE TABLE lines (file_path, context_id, line_no)")
        c2.execute("CREATE TABLE arcs (file_path, context_id, start_line, end_line)")
        c2.commit();
        c2.close()

        self.cov.combine_data()

        conn = sqlite3.connect(main_db)
        cur = conn.cursor()
        cur.execute("SELECT count(*) FROM contexts WHERE label='common'")
        count = cur.fetchone()[0]
        self.assertEqual(count, 1, "Should merge duplicate context labels")
        conn.close()

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