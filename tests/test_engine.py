import os
import threading
from src.engine import MiniCoverage
from tests.test_utils import BaseTestCase, MockFrame


class TestEngineCore(BaseTestCase):

    def setUp(self):
        super().setUp()
        self.cov = MiniCoverage(project_root=self.test_dir)

    def test_should_trace_filters(self):
        # File in project root
        in_project = os.path.join(self.test_dir, "script.py")
        self.assertTrue(self.cov._should_trace(in_project))

        # File outside project
        outside = "/tmp/other.py"
        self.assertFalse(self.cov._should_trace(outside))

        # Self exclusion
        self.assertFalse(self.cov._should_trace(__file__))

    def test_trace_function_line_capture(self):
        filename = os.path.join(self.test_dir, "test.py")
        frame = MockFrame(filename, 10)

        # Call trace manually
        self.cov.trace_function(frame, "line", None)

        self.assertIn(10, self.cov.trace_data['lines'][filename])

    def test_trace_function_arc_capture_same_file(self):
        filename = os.path.join(self.test_dir, "test.py")

        # Line 10
        f1 = MockFrame(filename, 10)
        self.cov.trace_function(f1, "line", None)

        # Line 11 (Next step)
        f2 = MockFrame(filename, 11)
        self.cov.trace_function(f2, "line", None)

        arcs = self.cov.trace_data['arcs'][filename]
        self.assertIn((10, 11), arcs)

    def test_trace_function_arc_cross_file_reset(self):
        file_a = os.path.join(self.test_dir, "a.py")
        file_b = os.path.join(self.test_dir, "b.py")

        # A:10
        self.cov.trace_function(MockFrame(file_a, 10), "line", None)
        # Jump to B:1
        self.cov.trace_function(MockFrame(file_b, 1), "line", None)

        # Should NOT record A:10 -> B:1
        self.assertEqual(len(self.cov.trace_data['arcs'][file_a]), 0)
        self.assertEqual(len(self.cov.trace_data['arcs'][file_b]), 0)

        # Step B:2
        self.cov.trace_function(MockFrame(file_b, 2), "line", None)
        # Should record B:1 -> B:2
        self.assertIn((1, 2), self.cov.trace_data['arcs'][file_b])

    def test_trace_function_ignored_events(self):
        filename = os.path.join(self.test_dir, "test.py")
        f = MockFrame(filename, 10)

        # Call with 'call' or 'return'
        self.cov.trace_function(f, "call", None)
        self.assertNotIn(filename, self.cov.trace_data['lines'])

    def test_save_data_no_data(self):
        # Should not throw
        self.cov.save_data()
        files = os.listdir(self.test_dir)
        # Assuming save_data doesn't create file if empty (implementation check)
        # The implementation says: if not lines and not arcs: return
        self.assertEqual(len(files), 0)

    def test_save_data_with_data(self):
        filename = os.path.join(self.test_dir, "test.py")
        self.cov.trace_data['lines'][filename].add(1)

        self.cov.save_data()

        files = [f for f in os.listdir(self.test_dir) if f.startswith(".coverage")]
        self.assertEqual(len(files), 1)

    def test_combine_data(self):
        # Manually create a .coverage pickle file
        import pickle
        import uuid

        data = {
            'lines': {'f1.py': {1, 2}},
            'arcs': {'f1.py': {(1, 2)}}
        }
        fname = f".coverage.{os.getpid()}.{uuid.uuid4().hex}"
        with open(os.path.join(self.test_dir, fname), 'wb') as f:
            pickle.dump(data, f)

        # Combine
        self.cov.combine_data()

        self.assertEqual(self.cov.trace_data['lines']['f1.py'], {1, 2})
        self.assertEqual(self.cov.trace_data['arcs']['f1.py'], {(1, 2)})
        # File should be deleted
        self.assertFalse(os.path.exists(os.path.join(self.test_dir, fname)))

    def test_config_integration_omit(self):
        # Setup config to omit 'ignored.py'
        cfg = """
[run]
omit = ignored.py
"""
        self.create_file(".coveragerc", cfg)

        # Re-init cov to load config
        cov = MiniCoverage(project_root=self.test_dir)

        ignored_file = os.path.join(self.test_dir, "ignored.py")
        self.assertFalse(cov._should_trace(ignored_file))

    def test_thread_local_storage(self):
        # Verify separate threads don't clobber 'last_line'
        filename = os.path.join(self.test_dir, "threaded.py")

        def t1_work():
            f1 = MockFrame(filename, 10)
            self.cov.trace_function(f1, "line", None)
            # Sleep to let t2 run
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

        th1.start()
        th2.start()
        th1.join()
        th2.join()

        arcs = self.cov.trace_data['arcs'][filename]
        # Should have 10->11 and 20->21
        self.assertIn((10, 11), arcs)
        self.assertIn((20, 21), arcs)
        # Should NOT have mixed arcs like 10->20 or 20->11
        self.assertNotIn((10, 20), arcs)
        self.assertNotIn((20, 11), arcs)