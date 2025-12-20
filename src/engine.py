import sys
import os
import collections
import threading
import multiprocessing
import sqlite3
import glob
import uuid
import fnmatch

# Relative imports assuming running as a package
from .source_parser import SourceParser
from .config_loader import ConfigLoader
from .metrics import StatementCoverage, BranchCoverage
from .reporters import ConsoleReporter, HtmlReporter


class MiniCoverage:
    def __init__(self, project_root=None, config_file=None):
        self.project_root = os.path.abspath(project_root) if project_root else os.getcwd()
        self.config_file = config_file

        # Load Configuration
        self.config_loader = ConfigLoader()
        self.config = self.config_loader.load_config(self.project_root, config_file)

        # In-memory storage for current process
        self.trace_data = {
            'lines': collections.defaultdict(set),
            'arcs': collections.defaultdict(set)
        }

        self.parser = SourceParser()
        self.metrics = [StatementCoverage(), BranchCoverage()]
        self.reporter = ConsoleReporter()
        self.html_reporter = HtmlReporter()

        self._cache_traceable = {}
        # Ensure we exclude the tool's own source files
        self.excluded_files = {os.path.abspath(__file__)}
        self.thread_local = threading.local()

        # Multiprocessing Data Identifier
        self.pid = os.getpid()
        self.uuid = uuid.uuid4().hex[:6]

    def _init_db(self, db_path):
        """Initializes the SQLite database schema."""
        conn = sqlite3.connect(db_path)
        cur = conn.cursor()
        cur.execute("""
                    CREATE TABLE IF NOT EXISTS lines
                    (
                        file_path
                        TEXT,
                        line_no
                        INTEGER,
                        PRIMARY
                        KEY
                    (
                        file_path,
                        line_no
                    )
                        )
                    """)
        cur.execute("""
                    CREATE TABLE IF NOT EXISTS arcs
                    (
                        file_path
                        TEXT,
                        start_line
                        INTEGER,
                        end_line
                        INTEGER,
                        PRIMARY
                        KEY
                    (
                        file_path,
                        start_line,
                        end_line
                    )
                        )
                    """)
        conn.commit()
        return conn

    def save_data(self):
        """Saves current coverage data to a unique SQLite file."""
        if not self.trace_data['lines'] and not self.trace_data['arcs']:
            return

        # Use a unique filename for this process to avoid locking contention during high concurrency
        base_name = self.config['data_file']
        filename = f"{base_name}.{self.pid}.{self.uuid}"

        try:
            conn = self._init_db(filename)
            cur = conn.cursor()

            # Batch Insert Lines
            line_data = []
            for file, lines in self.trace_data['lines'].items():
                for line in lines:
                    line_data.append((file, line))

            cur.executemany("INSERT OR IGNORE INTO lines (file_path, line_no) VALUES (?, ?)", line_data)

            # Batch Insert Arcs
            arc_data = []
            for file, arcs in self.trace_data['arcs'].items():
                for start, end in arcs:
                    arc_data.append((file, start, end))

            cur.executemany("INSERT OR IGNORE INTO arcs (file_path, start_line, end_line) VALUES (?, ?, ?)", arc_data)

            conn.commit()
            conn.close()
        except Exception as e:
            print(f"[!] Failed to save coverage data to DB: {e}")

    def combine_data(self):
        """Merges all partial DB files into the main database."""
        main_db = self.config['data_file']
        conn = self._init_db(main_db)
        cur = conn.cursor()

        # Find partial files: name.*.*
        # Note: glob pattern should match what save_data produces
        pattern = f"{main_db}.*.*"

        for filename in glob.glob(pattern):
            try:
                # Attach the partial DB
                # Note: 'attach' requires a simple alias name
                alias = f"partial_{uuid.uuid4().hex}"
                cur.execute(f"ATTACH DATABASE ? AS {alias}", (filename,))

                # Merge Lines
                cur.execute(f"INSERT OR IGNORE INTO lines SELECT * FROM {alias}.lines")

                # Merge Arcs
                cur.execute(f"INSERT OR IGNORE INTO arcs SELECT * FROM {alias}.arcs")

                conn.commit()
                cur.execute(f"DETACH DATABASE {alias}")

                # Cleanup merged file
                os.remove(filename)
            except sqlite3.OperationalError:
                # Lock issues or corrupt file
                pass
            except Exception as e:
                print(f"[!] Error combining {filename}: {e}")

        # Load combined data back into memory for reporting
        self._load_from_db(conn)
        conn.close()

    def _load_from_db(self, conn):
        """Populates self.trace_data from the given database connection."""
        cur = conn.cursor()

        # Load Lines
        cur.execute("SELECT file_path, line_no FROM lines")
        for file, line in cur.fetchall():
            self.trace_data['lines'][file].add(line)

        # Load Arcs
        cur.execute("SELECT file_path, start_line, end_line FROM arcs")
        for file, start, end in cur.fetchall():
            self.trace_data['arcs'][file].add((start, end))

    def _patch_multiprocessing(self):
        """Monkey-patches multiprocessing.Process to enable coverage in child processes."""
        if hasattr(multiprocessing, '_mini_coverage_patched'):
            return

        OriginalProcess = multiprocessing.Process

        # Capture context for the child process
        project_root = self.project_root
        config_file = self.config_file

        class CoverageProcess(OriginalProcess):
            def run(self):
                # Bootstrap coverage in the child process
                cov = MiniCoverage(project_root=project_root, config_file=config_file)

                sys.settrace(cov.trace_function)
                threading.settrace(cov.trace_function)

                try:
                    super().run()
                finally:
                    sys.settrace(None)
                    threading.settrace(None)
                    cov.save_data()

        multiprocessing.Process = CoverageProcess
        multiprocessing._mini_coverage_patched = True

    def trace_function(self, frame, event, arg):
        if event != 'line':
            return self.trace_function

        filename = frame.f_code.co_filename

        if filename not in self._cache_traceable:
            self._cache_traceable[filename] = self._should_trace(filename)

        if self._cache_traceable[filename]:
            lineno = frame.f_lineno

            if not hasattr(self.thread_local, 'last_line'):
                self.thread_local.last_line = None
                self.thread_local.last_file = None

            self.trace_data['lines'][filename].add(lineno)

            last_file = self.thread_local.last_file
            last_line = self.thread_local.last_line

            if last_file == filename and last_line is not None:
                self.trace_data['arcs'][filename].add((last_line, lineno))

            self.thread_local.last_line = lineno
            self.thread_local.last_file = filename
        else:
            if hasattr(self.thread_local, 'last_line'):
                self.thread_local.last_line = None
                self.thread_local.last_file = None

        return self.trace_function

    def _should_trace(self, filename):
        abs_path = os.path.abspath(filename)
        if not abs_path.startswith(self.project_root):
            return False
        if abs_path in self.excluded_files:
            return False

        rel_path = os.path.relpath(abs_path, self.project_root)
        for pattern in self.config['omit']:
            if fnmatch.fnmatch(rel_path, pattern):
                return False

        return True

    def analyze(self):
        full_results = {}
        all_files = set(self.trace_data['lines'].keys()) | set(self.trace_data['arcs'].keys())

        for filename in all_files:
            ast_tree, ignored_lines = self.parser.parse_source(filename)
            if not ast_tree:
                continue

            file_results = {}
            for metric in self.metrics:
                possible = metric.get_possible_elements(ast_tree, ignored_lines)

                if metric.get_name() == "Statement":
                    executed = self.trace_data['lines'][filename]
                elif metric.get_name() == "Branch":
                    executed = self.trace_data['arcs'][filename]
                else:
                    executed = set()

                stats = metric.calculate_stats(possible, executed)
                file_results[metric.get_name()] = stats

            full_results[filename] = file_results

        return full_results

    def run(self, script_path, script_args=None):
        abs_script_path = os.path.abspath(script_path)
        script_dir = os.path.dirname(abs_script_path)

        original_argv = sys.argv
        original_path = sys.path[:]

        sys.argv = [script_path] + (script_args if script_args else [])
        sys.path.insert(0, script_dir)

        try:
            with open(abs_script_path, 'rb') as f:
                code = compile(f.read(), abs_script_path, 'exec')

            self._patch_multiprocessing()

            sys.settrace(self.trace_function)
            threading.settrace(self.trace_function)

            exec_globals = {
                '__name__': '__main__',
                '__file__': abs_script_path,
                '__builtins__': __builtins__
            }
            exec(code, exec_globals)

        except SystemExit:
            pass
        except Exception as e:
            print(f"\n[!] Exception: {e}")
        finally:
            sys.settrace(None)
            threading.settrace(None)

            # Save data before combining
            self.save_data()

            sys.argv = original_argv
            sys.path = original_path

    def report(self):
        # Merge data from any partial DB files
        self.combine_data()

        results = self.analyze()
        self.reporter.print_report(results, self.project_root)
        self.html_reporter.generate(results, self.project_root)