import sys
import os
import logging
import threading
import multiprocessing
import types

from typing import Optional, List, Dict, Any, Set

# try to import the C extension
try:
    import minicov_tracer
except ImportError:
    minicov_tracer = None

from .analyzer import Analyzer
from .tracing.sys_monitoring import SysMonitoringTracer
from .tracing.sys_settrace import SysSetTraceTracer
from .trace_data import TraceContainer
from .path_manager import PathManager
from .source_parser import SourceParser
from .config_loader import ConfigLoader
from .metrics import StatementCoverage, BranchCoverage, ConditionCoverage
from .reporters import ConsoleReporter, HtmlReporter, XmlReporter, JsonReporter, BaseReporter
from .storage import CoverageStorage

_OriginalProcess = multiprocessing.Process


class CoverageProcess(_OriginalProcess):
    # class-level config to support pickling (set by _patch_multiprocessing)
    _subprocess_setup = {"project_root": None, "config_file": None}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._cov_project_root = self._subprocess_setup["project_root"]
        self._cov_config_file = self._subprocess_setup["config_file"]

    def run(self) -> None:
        if self._cov_project_root:
            cov = MiniCoverage(project_root=self._cov_project_root, config_file=self._cov_config_file)
            cov.start()
            try:
                super().run()
            finally:
                cov.stop()
        else:
            super().run()


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
        root = project_root if project_root else cwd

        self.config_file = config_file
        self.config_loader = ConfigLoader()

        # initialize PathManager early to handle root normalization
        # note: config is loaded with the raw root first, then PathManager canonicalizes it
        self.path_manager = PathManager(root, {})
        self.project_root = self.path_manager.project_root
        self.config: Dict[str, Any] = self.config_loader.load_config(self.project_root, config_file)
        self.path_manager.config = self.config

        # structure: {filename: {context_id: {data}}}
        # 'lines': set(lineno)
        # 'arcs': set((start, end))
        # 'instruction_arcs': set((from_offset, to_offset)) -> new for MC/DC
        self.trace_data = TraceContainer()

        self.current_context: str = "default"
        self.context_cache: Dict[str, int] = {"default": 0}
        self.reverse_context_cache: Dict[int, str] = {0: "default"}
        self._next_context_id: int = 1
        self._context_lock = threading.Lock()

        # initialize storage manager
        self.storage = CoverageStorage(self.config['data_file'])

        self.parser = SourceParser()
        self.metrics = [StatementCoverage(), BranchCoverage(), ConditionCoverage()]
        # ensure excluded files are also normalized
        self.excluded_files: Set[str] = set()
        self.analyzer = Analyzer(self.parser, self.metrics, self.config, self.path_manager, self.excluded_files)

        self.reporters: List[BaseReporter] = [
            ConsoleReporter(),
            HtmlReporter(output_dir="htmlcov"),
            XmlReporter(output_file="coverage.xml"),
            JsonReporter(output_file="coverage.json")
        ]

        self._cache_traceable: Dict[str, bool] = {}
        self.thread_local = threading.local()

        # initialize C Tracer if available
        self.c_tracer = None
        if minicov_tracer:
            try:
                # the C tracer takes 'self' (the engine) to access trace_data and caches
                self.c_tracer = minicov_tracer.Tracer(self)
                self.logger.info("Optimized C Tracer loaded.")
            except Exception as e:
                self.logger.warning(f"Failed to initialize C Tracer: {e}")

        # initialize tracers
        self.sys_monitoring_tracer = SysMonitoringTracer(self)
        self.sys_settrace_tracer = SysSetTraceTracer(self, self.c_tracer)

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

    def combine_data(self) -> None:
        """
        Merge all partial coverage database files into the main database.
        """
        # ensure current data is saved so it's included in the merge
        self.save_data()

        # delegate merge logic to storage, passing the path mapping function
        self.storage.combine(self.path_manager.map_path)

        # load merged data back into memory for analysis/reporting
        self.storage.load_into(self.trace_data, self.path_manager)

    def _patch_multiprocessing(self) -> None:
        """
        Monkey-patch multiprocessing.Process to support coverage in subprocesses.

        Ensures that child processes initialize their own coverage engine,
        collect data, and save it to disk upon exit.
        """
        # update global config for new processes
        CoverageProcess._subprocess_setup["project_root"] = self.project_root
        CoverageProcess._subprocess_setup["config_file"] = self.config_file

        if hasattr(multiprocessing, '_mini_coverage_patched'):
            return

        multiprocessing.Process = CoverageProcess
        multiprocessing._mini_coverage_patched = True  # type: ignore

    def start(self) -> None:
        """
        Start coverage tracing.
        Uses sys.monitoring for Python 3.12+, otherwise falls back to sys.settrace.
        """
        self._patch_multiprocessing()

        success = False
        if sys.version_info >= (3, 12):
            success = self.sys_monitoring_tracer.start()

        # fallback to sys.settrace if monitoring failed or is unavailable
        if not success:
            self.sys_settrace_tracer.start()

    def stop(self) -> None:
        """
        Stop coverage tracing and save data to disk.
        """
        if sys.version_info >= (3, 12):
            self.sys_monitoring_tracer.stop()

        self.sys_settrace_tracer.stop()
        self.save_data()

    def _record_line(self, filename: str, lineno: int, cid: int) -> None:
        self.trace_data.add_line(filename, cid, lineno)

        if not hasattr(self.thread_local, 'last_line'):
            self.thread_local.last_line = None
            self.thread_local.last_file = None

        last_file = self.thread_local.last_file
        last_line = self.thread_local.last_line

        if last_file == filename and last_line is not None:
            self.trace_data.add_arc(filename, cid, last_line, lineno)

        self.thread_local.last_line = lineno
        self.thread_local.last_file = filename

    def _record_opcode(self, filename: str, current_lasti: int, cid: int) -> None:
        if not hasattr(self.thread_local, 'last_lasti'):
            self.thread_local.last_lasti = None
            if not hasattr(self.thread_local, 'last_file'):
                self.thread_local.last_file = None
            # do not reset last_line here as it might be set by _record_line

        last_lasti = self.thread_local.last_lasti

        if last_lasti is not None and self.thread_local.last_file == filename:
            self.trace_data.add_instruction_arc(filename, cid, last_lasti, current_lasti)

        self.thread_local.last_lasti = current_lasti
        self.thread_local.last_file = filename

    def _should_trace(self, filename: str) -> bool:
        """
        Compatibility wrapper for C tracer which expects this method to exist on the engine.
        """
        return self.path_manager.should_trace(filename, self.excluded_files)

    def analyze(self) -> Dict[str, Dict[str, Any]]:
        """
        Perform static analysis and compare with collected dynamic data.

        Returns:
            dict: A mapping of filenames to metric statistics.
        """
        return self.analyzer.analyze(self.trace_data)

    def run(self, script_path: str, script_args: Optional[List[str]] = None) -> None:
        """
        Execute a target script under coverage tracking.

        Args:
            script_path (str): Path to the script to execute.
            script_args (list): List of command-line arguments to pass to the script.
        """
        abs_script_path = self.path_manager.canonicalize(script_path)
        script_dir = os.path.dirname(abs_script_path)

        original_argv = sys.argv
        original_path = sys.path[:]

        sys.argv = [script_path] + (script_args if script_args else [])
        sys.path.insert(0, script_dir)

        # create a module for the script to support multiprocessing pickling
        main_mod = types.ModuleType("__main__")
        main_mod.__file__ = abs_script_path
        main_mod.__builtins__ = __builtins__

        # backup existing __main__
        old_main = sys.modules['__main__']
        sys.modules['__main__'] = main_mod

        try:
            with open(abs_script_path, 'rb') as f:
                code = compile(f.read(), abs_script_path, 'exec')

            self.start()

            # execute code within the new module namespace
            exec(code, main_mod.__dict__)

        except SystemExit as e:
            self.logger.debug(f"SystemExit caught during execution: {e}")
            raise
        except Exception as e:
            self.logger.error(f"Exception during execution: {e}")
            raise
        finally:
            self.stop()
            sys.argv = original_argv
            sys.path = original_path
            sys.modules['__main__'] = old_main

    def report(self) -> None:
        """
        Combine data from parallel runs and generate reports using all registered reporters.
        """
        self.combine_data()
        results = self.analyze()

        for reporter in self.reporters:
            reporter.generate(results, self.project_root)
