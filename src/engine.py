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

from . import queries
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
        cwd = os.getcwd()
        if project_root:
            self.project_root = os.path.abspath(project_root)
        else:
            self.project_root = os.path.abspath(cwd)

        # Normalize for case-insensitive systems (Windows)
        self.project_root = os.path.normcase(self.project_root)

        self.config_file = config_file

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
        # Ensure excluded files are also normalized
        self.excluded_files: Set[str] = {os.path.normcase(os.path.abspath(__file__))}
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

        cur.execute(queries.INIT_CONTEXTS)
        cur.execute(queries.INIT_DEFAULT_CONTEXT)
        cur.execute(queries.INIT_LINES)
        cur.execute(queries.INIT_ARCS)
        cur.execute(queries.INIT_INSTRUCTION_ARCS)

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
            cur.executemany(queries.INSERT_CONTEXT, ctx_data)

            # batch insert lines
            line_data = []
            for file, ctx_map in self.trace_data['lines'].items():
                for cid, lines in ctx_map.items():
                    for line in lines:
                        line_data.append((file, cid, line))
            cur.executemany(queries.INSERT_LINE, line_data)

            # batch insert arcs
            arc_data = []
            for file, ctx_map in self.trace_data['arcs'].items():
                for cid, arcs in ctx_map.items():
                    for start, end in arcs:
                        arc_data.append((file, cid, start, end))
            cur.executemany(queries.INSERT_ARC, arc_data)

            # batch insert instruction arcs
            instr_data = []
            for file, ctx_map in self.trace_data['instruction_arcs'].items():
                for cid, arcs in ctx_map.items():
                    for start, end in arcs:
                        instr_data.append((file, cid, start, end))
            cur.executemany(queries.INSERT_INSTRUCTION_ARC, instr_data)

            conn.commit()
            conn.close()
        except Exception as e:
            print(f"[!] Failed to save coverage data to DB: {e}")

    def _map_path(self, path: str) -> str:
        """
        Remap a file path based on the [paths] configuration.
        Returns the canonical path if a match is found, otherwise the original.
        """
        path = os.path.normcase(path)
        for canonical, aliases in self.config.get('paths', {}).items():
            for alias in aliases:
                norm_alias = os.path.normcase(alias)
                if path.startswith(norm_alias):
                    # Replace the alias prefix with the canonical prefix
                    return path.replace(norm_alias, canonical, 1)
        return path

    def combine_data(self) -> None:
        """
        Merge all partial coverage database files into the main database.

        Handles attaching partial databases, copying data with context ID
        re-mapping via label matching, and cleaning up partial files.
        """
        main_db = self.config['data_file']
        conn = self._init_db(main_db)
        # Register the path mapping function for use in SQL queries
        conn.create_function("remap_path", 1, self._map_path)
        cur = conn.cursor()

        pattern = f"{main_db}.*.*"

        for filename in glob.glob(pattern):
            try:
                alias = f"partial_{uuid.uuid4().hex}"
                cur.execute(f"ATTACH DATABASE ? AS {alias}", (filename,))

                # copy new contexts from partial, ignoring existing labels
                cur.execute(queries.MERGE_CONTEXTS.format(alias=alias))

                # merge lines (re-mapping IDs via join on label)
                cur.execute(queries.MERGE_LINES.format(alias=alias))

                # merge arcs
                cur.execute(queries.MERGE_ARCS.format(alias=alias))

                # merge instruction arcs
                cur.execute(queries.MERGE_INSTRUCTION_ARCS.format(alias=alias))

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

        cur.execute(queries.SELECT_LINES)
        for file, line in cur.fetchall():
            self.trace_data['lines'][file][0].add(line)

        cur.execute(queries.SELECT_ARCS)
        for file, start, end in cur.fetchall():
            self.trace_data['arcs'][file][0].add((start, end))

        cur.execute(queries.SELECT_INSTRUCTION_ARCS)
        for file, start, end in cur.fetchall():
            self.trace_data['instruction_arcs'][file][0].add((start, end))

    def start(self) -> None:
        """
        Start coverage tracing.
        Uses sys.monitoring for Python 3.12+, otherwise falls back to sys.settrace.
        """
        # Set environment variable so subprocesses can bootstrap themselves
        # This replaces the need for monkey-patching if the environment is configured correctly
        if self.config_file:
            os.environ["MINICOV_CONFIG"] = os.path.abspath(self.config_file)

        # Also pass root so bootstrapper can find the src package if not installed
        os.environ["MINICOV_ROOT"] = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

        if sys.version_info >= (3, 12):
            self._start_sys_monitoring()
        else:
            # Use C tracer if available, else fallback to Python
            tracer = self.c_tracer if self.c_tracer else self.trace_function
            sys.settrace(tracer)
            threading.settrace(tracer)

    def stop(self) -> None:
        """
        Stop coverage tracing and save data to disk.
        """
        if sys.version_info >= (3, 12):
            self._stop_sys_monitoring()
        else:
            sys.settrace(None)
            threading.settrace(None)

        self.save_data()

    def _start_sys_monitoring(self) -> None:
        """
        Enable sys.monitoring (Python 3.12+).
        """
        try:
            import sys.monitoring

            tool_id = sys.monitoring.COVERAGE_ID
            sys.monitoring.use_tool_id(tool_id, "MiniCoverage")

            # Register callbacks
            # Monitor PY_START to filter files efficiently
            sys.monitoring.register_callback(tool_id, sys.monitoring.events.PY_START, self._monitor_py_start)
            sys.monitoring.register_callback(tool_id, sys.monitoring.events.LINE, self._monitor_line)
            sys.monitoring.register_callback(tool_id, sys.monitoring.events.BRANCH, self._monitor_branch)

            # Enable PY_START globally. Local events will be enabled in _monitor_py_start.
            sys.monitoring.set_events(tool_id, sys.monitoring.events.PY_START)

        except Exception as e:
            print(f"[Warning] sys.monitoring failed: {e}. Falling back to sys.settrace.")
            # Fallback logic could be complex here as start() already chose this path.
            # Ideally we would fallback recursively, but for MVP we log.

    def _stop_sys_monitoring(self) -> None:
        """
        Disable sys.monitoring.
        """
        try:
            import sys.monitoring
            tool_id = sys.monitoring.COVERAGE_ID
            sys.monitoring.set_events(tool_id, 0)
            sys.monitoring.free_tool_id(tool_id)
        except Exception:
            pass

    def _monitor_py_start(self, code: types.CodeType, instruction_offset: int) -> Any:
        """
        sys.monitoring callback for PY_START.
        Determines if a code object should be traced.
        """
        filename = code.co_filename
        # Normalize path for comparison (handling short/long/casing)
        abs_filename = os.path.normcase(os.path.abspath(filename))

        if filename not in self._cache_traceable:
            self._cache_traceable[filename] = self._should_trace(abs_filename)

        if self._cache_traceable[filename]:
            import sys.monitoring
            # Enable LINE and BRANCH events for this code object
            sys.monitoring.set_local_events(sys.monitoring.COVERAGE_ID, code,
                                            sys.monitoring.events.LINE | sys.monitoring.events.BRANCH)
        else:
            import sys.monitoring
            sys.monitoring.set_local_events(sys.monitoring.COVERAGE_ID, code, 0)

    def _monitor_line(self, code: types.CodeType, line_number: int) -> Any:
        """
        sys.monitoring callback for LINE events.
        """
        filename = code.co_filename
        cid = self._get_current_context_id()

        self.trace_data['lines'][filename][cid].add(line_number)

        # Track line transitions (arcs) manually as sys.monitoring doesn't give 'last line'
        # We rely on thread local storage
        if not hasattr(self.thread_local, 'last_line'):
            self.thread_local.last_line = None
            self.thread_local.last_file = None

        last_file = self.thread_local.last_file
        last_line = self.thread_local.last_line

        if last_file == filename and last_line is not None:
            self.trace_data['arcs'][filename][cid].add((last_line, line_number))

        self.thread_local.last_line = line_number
        self.thread_local.last_file = filename

        return None  # Keep event enabled

    def _monitor_branch(self, code: types.CodeType, from_offset: int, to_offset: int) -> Any:
        """
        sys.monitoring callback for BRANCH events.
        """
        filename = code.co_filename
        cid = self._get_current_context_id()

        self.trace_data['instruction_arcs'][filename][cid].add((from_offset, to_offset))
        return None

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
        # Normalize for Windows to handle C:\ vs c:\
        abs_path = os.path.normcase(abs_path)

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
        # Normalize path for consistency
        abs_script_path = os.path.abspath(script_path)
        script_dir = os.path.dirname(abs_script_path)

        original_argv = sys.argv
        original_path = sys.path[:]

        sys.argv = [script_path] + (script_args if script_args else [])
        sys.path.insert(0, script_dir)

        try:
            with open(abs_script_path, 'rb') as f:
                code = compile(f.read(), abs_script_path, 'exec')

            self.start()

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
            self.stop()
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