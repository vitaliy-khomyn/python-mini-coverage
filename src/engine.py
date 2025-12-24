import sys
import os
import collections
import threading
import multiprocessing
import sqlite3
import glob
import uuid
import fnmatch
import types
from typing import Optional, List, Dict, Any, Set, Tuple

# Try to import the C extension
try:
    import minicov_tracer
except ImportError:
    minicov_tracer = None

from .source_parser import SourceParser
from .config_loader import ConfigLoader
from .metrics import StatementCoverage, BranchCoverage, ConditionCoverage, BytecodeControlFlow
from .reporters import ConsoleReporter, HtmlReporter, XmlReporter, JsonReporter, BaseReporter


class MiniCoverage:
    def __init__(self, project_root: Optional[str] = None, config_file: Optional[str] = None) -> None:
        """
        Initialize the coverage engine.

        Args:
            project_root (str): The root directory to restrict tracing to.
            config_file (str): Optional path to a configuration file.
        """
        self.project_root: str = os.path.abspath(project_root) if project_root else os.getcwd()
        self.config_file: Optional[str] = config_file

        self.config_loader = ConfigLoader()
        self.config: Dict[str, Any] = self.config_loader.load_config(self.project_root, config_file)

        # structure: {filename: {context_id: {data}}}
        # 'lines': set(lineno)
        # 'arcs': set((start, end))
        # 'instruction_arcs': set((from_offset, to_offset)) -> New for MC/DC
        self.trace_data: Dict[str, Dict[Any, Any]] = {
            'lines': collections.defaultdict(lambda: collections.defaultdict(set)),
            'arcs': collections.defaultdict(lambda: collections.defaultdict(set)),
            'instruction_arcs': collections.defaultdict(lambda: collections.defaultdict(set))
        }

        self.current_context: str = "default"
        self.context_cache: Dict[str, int] = {"default": 0}
        self.reverse_context_cache: Dict[int, str] = {0: "default"}
        self._next_context_id: int = 1
        self._context_lock = threading.Lock()

        self.parser = SourceParser()
        self.metrics = [StatementCoverage(), BranchCoverage(), ConditionCoverage()]

        self.reporters: List[BaseReporter] = [
            ConsoleReporter(),
            HtmlReporter(output_dir="htmlcov"),
            XmlReporter(output_file="coverage.xml"),
            JsonReporter(output_file="coverage.json")
        ]

        self._cache_traceable: Dict[str, bool] = {}
        self.excluded_files: Set[str] = {os.path.abspath(__file__)}
        self.thread_local = threading.local()

        self.pid: int = os.getpid()
        self.uuid: str = uuid.uuid4().hex[:6]

        # Initialize C Tracer if available
        self.c_tracer = None
        if minicov_tracer:
            try:
                # The C tracer takes 'self' (the engine) to access trace_data and caches
                self.c_tracer = minicov_tracer.Tracer(self)
                print("[Info] Optimized C Tracer loaded.")
            except Exception as e:
                print(f"[Warning] Failed to initialize C Tracer: {e}")

    def switch_context(self, context_label: str) -> None:
        """
        Switch the current recording context.

        If the context label is new, assigns a new ID.
        Thread-safe regarding context ID assignment.
        """
        if context_label == self.current_context:
            return

        with self._context_lock:
            if context_label not in self.context_cache:
                cid = self._next_context_id
                self.context_cache[context_label] = cid
                self.reverse_context_cache[cid] = context_label
                self._next_context_id += 1

            self.current_context = context_label

    def _get_current_context_id(self) -> int:
        """
        Retrieve the integer ID for the active context.
        """
        # optimization: fast lookup without lock if possible (GIL makes dict read atomic-ish)
        return self.context_cache.get(self.current_context, 0)

    def _init_db(self, db_path: str) -> sqlite3.Connection:
        """
        Initialize the SQLite database schema.

        Creates 'contexts', 'lines', 'arcs', and 'instruction_arcs' tables.
        """
        conn = sqlite3.connect(db_path)
        cur = conn.cursor()

        cur.execute("""
                    CREATE TABLE IF NOT EXISTS contexts
                    (
                        id    INTEGER PRIMARY KEY,
                        label TEXT UNIQUE
                    )
                    """)

        # insert default context if not exists
        cur.execute("INSERT OR IGNORE INTO contexts (id, label) VALUES (0, 'default')")

        cur.execute("""
                    CREATE TABLE IF NOT EXISTS lines
                    (
                        file_path  TEXT,
                        context_id INTEGER,
                        line_no    INTEGER,
                        PRIMARY KEY (file_path, context_id, line_no),
                        FOREIGN KEY (context_id) REFERENCES contexts (id)
                    )
                    """)
        cur.execute("""
                    CREATE TABLE IF NOT EXISTS arcs
                    (
                        file_path  TEXT,
                        context_id INTEGER,
                        start_line INTEGER,
                        end_line   INTEGER,
                        PRIMARY KEY (file_path, context_id, start_line, end_line),
                        FOREIGN KEY (context_id) REFERENCES contexts (id)
                    )
                    """)
        cur.execute("""
                    CREATE TABLE IF NOT EXISTS instruction_arcs
                    (
                        file_path   TEXT,
                        context_id  INTEGER,
                        from_offset INTEGER,
                        to_offset   INTEGER,
                        PRIMARY KEY (file_path, context_id, from_offset, to_offset),
                        FOREIGN KEY (context_id) REFERENCES contexts (id)
                    )
                    """)
        conn.commit()
        return conn

    def save_data(self) -> None:
        """
        Dump the in-memory coverage data to a unique SQLite file.

        This prevents locking contention by writing to a unique filename
        based on PID and UUID.
        """
        has_data = any(self.trace_data['lines'].values()) or any(self.trace_data['arcs'].values())
        if not has_data:
            return

        base_name = self.config['data_file']
        filename = f"{base_name}.{self.pid}.{self.uuid}"

        try:
            conn = self._init_db(filename)
            cur = conn.cursor()

            # sync contexts
            ctx_data = [(cid, label) for label, cid in self.context_cache.items()]
            cur.executemany("INSERT OR IGNORE INTO contexts (id, label) VALUES (?, ?)", ctx_data)

            # batch insert lines
            line_data = []
            for file, ctx_map in self.trace_data['lines'].items():
                for cid, lines in ctx_map.items():
                    for line in lines:
                        line_data.append((file, cid, line))
            cur.executemany("INSERT OR IGNORE INTO lines (file_path, context_id, line_no) VALUES (?, ?, ?)", line_data)

            # batch insert arcs
            arc_data = []
            for file, ctx_map in self.trace_data['arcs'].items():
                for cid, arcs in ctx_map.items():
                    for start, end in arcs:
                        arc_data.append((file, cid, start, end))
            cur.executemany(
                "INSERT OR IGNORE INTO arcs (file_path, context_id, start_line, end_line) VALUES (?, ?, ?, ?)",
                arc_data)

            # batch insert instruction arcs
            instr_data = []
            for file, ctx_map in self.trace_data['instruction_arcs'].items():
                for cid, arcs in ctx_map.items():
                    for start, end in arcs:
                        instr_data.append((file, cid, start, end))
            cur.executemany(
                "INSERT OR IGNORE INTO instruction_arcs (file_path, context_id, from_offset, to_offset) VALUES (?, ?, ?, ?)",
                instr_data)

            conn.commit()
            conn.close()
        except Exception as e:
            print(f"[!] Failed to save coverage data to DB: {e}")

    def combine_data(self) -> None:
        """
        Merge all partial coverage database files into the main database.

        Handles attaching partial databases, copying data with context ID
        re-mapping via label matching, and cleaning up partial files.
        """
        main_db = self.config['data_file']
        conn = self._init_db(main_db)
        cur = conn.cursor()

        pattern = f"{main_db}.*.*"

        for filename in glob.glob(pattern):
            try:
                alias = f"partial_{uuid.uuid4().hex}"
                cur.execute(f"ATTACH DATABASE ? AS {alias}", (filename,))

                # copy new contexts from partial, ignoring existing labels
                cur.execute(f"INSERT OR IGNORE INTO contexts (label) SELECT label FROM {alias}.contexts")

                # merge lines (re-mapping IDs via join on label)
                sql_lines = f"""
                INSERT OR IGNORE INTO lines (file_path, context_id, line_no)
                SELECT l.file_path, main_c.id, l.line_no
                FROM {alias}.lines l
                JOIN {alias}.contexts partial_c ON l.context_id = partial_c.id
                JOIN contexts main_c ON partial_c.label = main_c.label
                """
                cur.execute(sql_lines)

                # merge arcs
                sql_arcs = f"""
                INSERT OR IGNORE INTO arcs (file_path, context_id, start_line, end_line)
                SELECT a.file_path, main_c.id, a.start_line, a.end_line
                FROM {alias}.arcs a
                JOIN {alias}.contexts partial_c ON a.context_id = partial_c.id
                JOIN contexts main_c ON partial_c.label = main_c.label
                """
                cur.execute(sql_arcs)

                # merge instruction arcs
                sql_instr = f"""
                INSERT OR IGNORE INTO instruction_arcs (file_path, context_id, from_offset, to_offset)
                SELECT a.file_path, main_c.id, a.from_offset, a.to_offset
                FROM {alias}.instruction_arcs a
                JOIN {alias}.contexts partial_c ON a.context_id = partial_c.id
                JOIN contexts main_c ON partial_c.label = main_c.label
                """
                cur.execute(sql_instr)

                conn.commit()
                cur.execute(f"DETACH DATABASE {alias}")
                os.remove(filename)
            except sqlite3.OperationalError:
                pass
            except Exception as e:
                print(f"[!] Error combining {filename}: {e}")

        self._load_from_db(conn)
        conn.close()

    def _load_from_db(self, conn: sqlite3.Connection) -> None:
        """
        Populate in-memory trace data from the database.

        Currently flattens data into the default context for reporting purposes.
        """
        cur = conn.cursor()

        cur.execute("SELECT file_path, line_no FROM lines")
        for file, line in cur.fetchall():
            self.trace_data['lines'][file][0].add(line)

        cur.execute("SELECT file_path, start_line, end_line FROM arcs")
        for file, start, end in cur.fetchall():
            self.trace_data['arcs'][file][0].add((start, end))

        cur.execute("SELECT file_path, from_offset, to_offset FROM instruction_arcs")
        for file, start, end in cur.fetchall():
            self.trace_data['instruction_arcs'][file][0].add((start, end))

    def _patch_multiprocessing(self) -> None:
        """
        Monkey-patch multiprocessing.Process to support coverage in subprocesses.

        Ensures that child processes initialize their own coverage engine,
        collect data, and save it to disk upon exit.
        """
        if hasattr(multiprocessing, '_mini_coverage_patched'):
            return

        OriginalProcess = multiprocessing.Process
        project_root = self.project_root
        config_file = self.config_file

        class CoverageProcess(OriginalProcess):
            def run(self) -> None:
                cov = MiniCoverage(project_root=project_root, config_file=config_file)

                # Use C tracer if available
                tracer = cov.c_tracer if cov.c_tracer else cov.trace_function

                sys.settrace(tracer)
                threading.settrace(tracer)
                try:
                    super().run()
                finally:
                    sys.settrace(None)
                    threading.settrace(None)
                    cov.save_data()

        multiprocessing.Process = CoverageProcess
        multiprocessing._mini_coverage_patched = True  # type: ignore

    def trace_function(self, frame: types.FrameType, event: str, arg: Any) -> Any:
        """
        The main system trace callback (Python fallback).

        Args:
            frame: The current stack frame.
            event: The trace event (e.g., 'line', 'call').
            arg: Dependent on event type (unused for 'line').
        """
        # Enable opcode tracing for this frame
        if event == 'call':
            frame.f_trace_opcodes = True
            return self.trace_function

        if event not in ('line', 'opcode'):
            return self.trace_function

        filename = frame.f_code.co_filename

        if filename not in self._cache_traceable:
            self._cache_traceable[filename] = self._should_trace(filename)

        if self._cache_traceable[filename]:
            cid = self._get_current_context_id()

            if not hasattr(self.thread_local, 'last_line'):
                self.thread_local.last_line = None
                self.thread_local.last_file = None
                self.thread_local.last_lasti = None

            # 1. Line Trace
            if event == 'line':
                lineno = frame.f_lineno
                self.trace_data['lines'][filename][cid].add(lineno)

                last_file = self.thread_local.last_file
                last_line = self.thread_local.last_line

                if last_file == filename and last_line is not None:
                    self.trace_data['arcs'][filename][cid].add((last_line, lineno))

                self.thread_local.last_line = lineno
                self.thread_local.last_file = filename

            # 2. Opcode Trace (For MC/DC)
            current_lasti = frame.f_lasti
            last_lasti = self.thread_local.last_lasti

            if last_lasti is not None and self.thread_local.last_file == filename:
                self.trace_data['instruction_arcs'][filename][cid].add((last_lasti, current_lasti))

            self.thread_local.last_lasti = current_lasti
            self.thread_local.last_file = filename

        else:
            if hasattr(self.thread_local, 'last_line'):
                self.thread_local.last_line = None
                self.thread_local.last_file = None
                self.thread_local.last_lasti = None

        return self.trace_function

    def _should_trace(self, filename: str) -> bool:
        """
        Determine if a file should be tracked based on project root and exclusions.
        """
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

    def analyze(self) -> Dict[str, Dict[str, Any]]:
        """
        Perform static analysis and compare with collected dynamic data.

        Returns:
            dict: A mapping of filenames to metric statistics.
        """
        full_results = {}
        all_files = set(self.trace_data['lines'].keys()) | set(self.trace_data['arcs'].keys())

        exclude_patterns = self.config.get('exclude_lines', set())

        for filename in all_files:
            ast_tree, ignored_lines = self.parser.parse_source(filename, exclude_patterns)
            if not ast_tree:
                continue

            code_obj = self.parser.compile_source(filename)

            file_results = {}
            for metric in self.metrics:
                possible = set()
                executed = set()

                if metric.get_name() == "Statement":
                    possible = metric.get_possible_elements(ast_tree, ignored_lines)
                    for ctx_lines in self.trace_data['lines'][filename].values():
                        executed.update(ctx_lines)
                elif metric.get_name() == "Branch":
                    possible = metric.get_possible_elements(ast_tree, ignored_lines)
                    for ctx_arcs in self.trace_data['arcs'][filename].values():
                        executed.update(ctx_arcs)
                elif metric.get_name() == "Condition":
                    # Condition Coverage needs Code Object + Instruction Arcs
                    possible = metric.get_possible_elements(code_obj, ignored_lines)  # type: ignore
                    for ctx_instr in self.trace_data['instruction_arcs'][filename].values():
                        executed.update(ctx_instr)

                stats = metric.calculate_stats(possible, executed)
                file_results[metric.get_name()] = stats

            full_results[filename] = file_results

        return full_results

    def run(self, script_path: str, script_args: Optional[List[str]] = None) -> None:
        """
        Execute a target script under coverage tracking.

        Args:
            script_path (str): Path to the script to execute.
            script_args (list): List of command-line arguments to pass to the script.
        """
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

            # Use C tracer if available, else fallback to Python
            tracer = self.c_tracer if self.c_tracer else self.trace_function

            sys.settrace(tracer)
            threading.settrace(tracer)

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
            self.save_data()
            sys.argv = original_argv
            sys.path = original_path

    def report(self) -> None:
        """
        Combine data from parallel runs and generate reports using all registered reporters.
        """
        self.combine_data()
        results = self.analyze()

        for reporter in self.reporters:
            reporter.generate(results, self.project_root)