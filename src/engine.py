import sys
import os
import collections
import logging
import threading
import multiprocessing
import fnmatch
import types
from typing import Optional, List, Dict, Any, Set

# try to import the C extension
try:
    import minicov_tracer
except ImportError:
    minicov_tracer = None

from .source_parser import SourceParser
from .config_loader import ConfigLoader
from .metrics import StatementCoverage, BranchCoverage, ConditionCoverage
from .reporters import ConsoleReporter, HtmlReporter, XmlReporter, JsonReporter, BaseReporter
from .storage import CoverageStorage


class MiniCoverage:
    def __init__(self, project_root: Optional[str] = None, config_file: Optional[str] = None) -> None:
        """
        Initialize the coverage engine.

        Args:
            project_root (str): The root directory to restrict tracing to.
            config_file (str): Optional path to a configuration file.
        """
        self.logger = logging.getLogger(__name__)

        cwd = os.getcwd()
        if project_root:
            # use realpath to ensure having the canonical path (resolves symlinks and etc)
            self.project_root = os.path.realpath(project_root)
        else:
            self.project_root = os.path.realpath(cwd)

        # normalize for case-insensitive systems (Windows)
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

        # initialize storage manager
        self.storage = CoverageStorage(self.config['data_file'])

        self.parser = SourceParser()
        self.metrics = [StatementCoverage(), BranchCoverage(), ConditionCoverage()]

        self.reporters: List[BaseReporter] = [
            ConsoleReporter(),
            HtmlReporter(output_dir="htmlcov"),
            XmlReporter(output_file="coverage.xml"),
            JsonReporter(output_file="coverage.json")
        ]

        self._cache_traceable: Dict[str, bool] = {}
        # ensure excluded files are also normalized
        self.excluded_files: Set[str] = {os.path.normcase(os.path.realpath(__file__))}
        self.thread_local = threading.local()

        # initialize C Tracer if available
        self.c_tracer = None
        if minicov_tracer:
            try:
                # The C tracer takes 'self' (the engine) to access trace_data and caches
                self.c_tracer = minicov_tracer.Tracer(self)
                self.logger.info("Optimized C Tracer loaded.")
            except Exception as e:
                self.logger.warning(f"Failed to initialize C Tracer: {e}")

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

    def save_data(self) -> None:
        """
        Dump the in-memory coverage data to a unique SQLite file via Storage Manager.
        """
        self.storage.save(self.trace_data, self.context_cache)

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
                    # We use standard string replacement for simplicity
                    return path.replace(norm_alias, canonical, 1)
        return path

    def combine_data(self) -> None:
        """
        Merge all partial coverage database files into the main database.
        """
        # Delegate merge logic to storage, passing the path mapping function
        self.storage.combine(self._map_path)

        # Load merged data back into memory for analysis/reporting
        self.storage.load_into(self.trace_data)

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
                # ensure child process starts the correct backend
                cov.start()
                try:
                    super().run()
                finally:
                    cov.stop()

        multiprocessing.Process = CoverageProcess
        multiprocessing._mini_coverage_patched = True  # type: ignore

    def start(self) -> None:
        """
        Start coverage tracing.
        Uses sys.monitoring for Python 3.12+, otherwise falls back to sys.settrace.
        """
        self._patch_multiprocessing()

        use_monitoring = False
        if sys.version_info >= (3, 12):
            use_monitoring = self._start_sys_monitoring()

        # fallback to sys.settrace if monitoring failed or is unavailable
        if not use_monitoring:
            tracer = self.c_tracer if self.c_tracer else self.trace_function
            sys.settrace(tracer)
            threading.settrace(tracer)

    def stop(self) -> None:
        """
        Stop coverage tracing and save data to disk.
        """
        if sys.version_info >= (3, 12):
            self._stop_sys_monitoring()

        # always unset settrace as well, just in case fallback was active
        sys.settrace(None)
        threading.settrace(None)

        self.save_data()

    def _start_sys_monitoring(self) -> bool:
        """
        Enable sys.monitoring (Python 3.12+).
        Returns True if successful, False otherwise.
        """
        try:
            import sys.monitoring

            tool_id = sys.monitoring.COVERAGE_ID
            sys.monitoring.use_tool_id(tool_id, "MiniCoverage")

            # register callbacks
            # monitor PY_START to filter files efficiently
            sys.monitoring.register_callback(tool_id, sys.monitoring.events.PY_START, self._monitor_py_start)
            sys.monitoring.register_callback(tool_id, sys.monitoring.events.LINE, self._monitor_line)
            sys.monitoring.register_callback(tool_id, sys.monitoring.events.BRANCH, self._monitor_branch)

            # enable PY_START globally. Local events will be enabled in _monitor_py_start.
            sys.monitoring.set_events(tool_id, sys.monitoring.events.PY_START)
            return True

        except Exception as e:
            self.logger.warning(f"sys.monitoring failed: {e}. Falling back to sys.settrace.")
            return False

    def _stop_sys_monitoring(self) -> None:
        """
        Disable sys.monitoring.
        """
        try:
            import sys.monitoring
            tool_id = sys.monitoring.COVERAGE_ID
            sys.monitoring.set_events(tool_id, 0)
            sys.monitoring.free_tool_id(tool_id)
        except Exception as e:
            self.logger.debug(f"Error stopping sys.monitoring: {e}")

    def _monitor_py_start(self, code: types.CodeType, instruction_offset: int) -> Any:
        """
        sys.monitoring callback for PY_START.
        Determines if a code object should be traced.
        """
        filename = code.co_filename
        # normalize path for comparison (handling short/long/casing)
        abs_filename = os.path.normcase(os.path.realpath(filename))

        if filename not in self._cache_traceable:
            self._cache_traceable[filename] = self._should_trace(abs_filename)

        if self._cache_traceable[filename]:
            import sys.monitoring
            # enable LINE and BRANCH events for this code object
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

        # track line transitions (arcs) manually as sys.monitoring doesn't give 'last line'
        # thread local storage
        if not hasattr(self.thread_local, 'last_line'):
            self.thread_local.last_line = None
            self.thread_local.last_file = None

        last_file = self.thread_local.last_file
        last_line = self.thread_local.last_line

        if last_file == filename and last_line is not None:
            self.trace_data['arcs'][filename][cid].add((last_line, line_number))

        self.thread_local.last_line = line_number
        self.thread_local.last_file = filename

        return None  # keep event enabled

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
        # enable opcode tracing for this frame
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

            # 1. line trace
            if event == 'line':
                lineno = frame.f_lineno
                self.trace_data['lines'][filename][cid].add(lineno)

                last_file = self.thread_local.last_file
                last_line = self.thread_local.last_line

                if last_file == filename and last_line is not None:
                    self.trace_data['arcs'][filename][cid].add((last_line, lineno))

                self.thread_local.last_line = lineno
                self.thread_local.last_file = filename

            # 2. Opcode trace (for MC/DC)
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
        # Use realpath to ensure consistent behavior across OS environments (canonical paths)
        # This matches how paths are treated in tests (test_utils uses realpath)
        # BUT we still use abspath in run() to preserve short paths if passed by user.
        # This function bridges the gap.
        abs_path = os.path.realpath(filename)
        # normalize for Windows to handle C:\ vs c:\
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
            # re-verify traceability with normalized paths to avoid processing artifacts
            if not self._should_trace(filename):
                continue

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
        # Normalize path for consistency, but use abspath to respect user input format (e.g. short paths)
        # This fixes KeyError issues where test runner uses short paths but we forced realpath previously.
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

        except SystemExit as e:
            self.logger.debug(f"SystemExit caught during execution: {e}")
        except Exception as e:
            self.logger.error(f"Exception during execution: {e}")
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
