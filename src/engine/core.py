import sys
import os
import logging
import shutil
import threading
import multiprocessing
import types

from typing import Optional, List, Dict, Any, Set

# try to import the C extension
try:
    import minicov_tracer
except ImportError:
    minicov_tracer = None

from .config import CoverageConfig
from .report_manager import ReportManager
from .analyzer import Analyzer
from ..tracing.sys_monitoring import SysMonitoringTracer
from ..tracing.sys_settrace import SysSetTraceTracer
from .trace_data import TraceContainer
from .path_manager import PathManager
from .source_parser import SourceParser
from .config_loader import ConfigLoader
from ..metrics import StatementCoverage, BranchCoverage, ConditionCoverage, FunctionCoverage, LoopCoverage, ClassCoverage
from ..metrics.call_site import CallSiteCoverage
from ..metrics.exception import ExceptionCoverage
from ..metrics.return_coverage import ReturnCoverage
from ..metrics.mmcdc import MMCDCCoverage
from .storage import CoverageStorage

_OriginalProcess = multiprocessing.Process

# thread-local storage to prevent race conditions when starting multiple engines
_config_local = threading.local()


class TraceState(threading.local):
    def __init__(self) -> None:
        self.last_line: Optional[int] = None
        self.last_file: Optional[str] = None
        self.last_lasti: Optional[int] = None
        self.last_code_id: Optional[int] = None


class CoverageProcess(_OriginalProcess):
    # class-level config to support pickling (set by _patch_multiprocessing)
    _subprocess_setup = {"project_root": None, "config_file": None}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # prefer thread-local config if available (handles concurrent starts)
        if hasattr(_config_local, "project_root"):
            self._cov_project_root = _config_local.project_root
            self._cov_config_file = _config_local.config_file
        else:
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
    def __init__(self, project_root: Optional[str] = None, config_file: Optional[str] = None, erase_on_start: bool = False) -> None:
        """
        Initialize the coverage engine.

        Args:
            project_root (str): The root directory to restrict tracing to.
            config_file (str): Optional path to a configuration file.
            erase_on_start (bool): If True, delete existing data file and reports before starting.
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
        self.config: CoverageConfig = self.config_loader.load_config(self.project_root, config_file)
        self.path_manager.config = self.config

        if erase_on_start:
            self._erase_data()

        # structure: {filename: {context_id: {data}}}
        # 'lines': set(lineno)
        # 'arcs': set((start, end))
        # 'instruction_arcs': set((from_offset, to_offset)) -> new for Condition Coverage
        self.trace_data = TraceContainer()

        self.current_context: str = "default"
        self.context_cache: Dict[str, int] = {"default": 0}
        self.reverse_context_cache: Dict[int, str] = {0: "default"}
        self._next_context_id: int = 1
        self._context_lock = threading.Lock()

        # initialize storage manager
        self.storage = CoverageStorage(self.config.data_file)

        self.parser = SourceParser()
        self._initialize_metrics()
        self._setup_exclusions()

        self.analyzer = Analyzer(self.parser, self.metrics, self.config, self.path_manager, self.excluded_files)

        self.report_manager = ReportManager(self.config)

        self._cache_traceable: Dict[str, bool] = {}
        self.thread_local = TraceState()

        self._initialize_tracers()

    def _initialize_metrics(self) -> None:
        self.metrics = [
            StatementCoverage(),
            BranchCoverage(),
            ConditionCoverage(),
            FunctionCoverage(),
            LoopCoverage(),
            ClassCoverage(),
            CallSiteCoverage(),
            ExceptionCoverage(),
            ReturnCoverage(),
            MMCDCCoverage(),
        ]

    def _setup_exclusions(self) -> None:
        # ensure excluded files are also normalized
        self.excluded_files: Set[str] = set()

        # auto-exclude the tool's own source code to prevent self-instrumentation
        # get the 'src' directory (grandparent of this file)
        _src_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        self._lib_root = self.path_manager.canonicalize(_src_dir)
        self.excluded_files.add(self._lib_root)

    def _initialize_tracers(self) -> None:
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

    def _erase_data(self) -> None:
        """
        Erase previously collected coverage data and reports.
        """
        def _safe_erase(path: str, is_dir: bool, desc: str) -> None:
            if path and os.path.exists(path):
                try:
                    shutil.rmtree(path) if is_dir else os.remove(path)
                    self.logger.info(f"Erased old {desc}: {path}")
                except OSError as e:
                    self.logger.warning(f"Failed to erase {desc}: {e}")

        _safe_erase(self.config.data_file, False, "coverage data")
        _safe_erase(os.path.join(self.project_root, "htmlcov"), True, "HTML report directory")
        _safe_erase(os.path.join(self.project_root, "coverage.xml"), False, "XML report")
        _safe_erase(os.path.join(self.project_root, "coverage.json"), False, "JSON report")

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

    def _start_new_frame(self) -> None:
        """
        Resets thread-local history to prevent arcs between unrelated functions.
        Called by tracers on function entry events ('call', 'PY_START', 'PY_RESUME').
        """
        self.thread_local.last_line = None
        self.thread_local.last_lasti = None
        self.thread_local.last_file = None
        self.thread_local.last_code_id = None

    def save_data(self) -> None:
        """
        Dump the in-memory coverage data to a unique SQLite file via Storage Manager.
        """
        self.storage.save(self.trace_data, self.context_cache, self.path_manager.map_path)

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

        # set thread-local config for CoverageProcess initialization
        _config_local.project_root = self.project_root
        _config_local.config_file = self.config_file

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
        # clean up thread-local config
        if hasattr(_config_local, "project_root"):
            del _config_local.project_root
        if hasattr(_config_local, "config_file"):
            del _config_local.config_file

        if sys.version_info >= (3, 12):
            self.sys_monitoring_tracer.stop()

        self.sys_settrace_tracer.stop()
        self.save_data()

    def _record_line(self, filename: str, lineno: int, cid: int) -> None:
        self.trace_data.add_line(filename, cid, lineno)

        last_file = self.thread_local.last_file
        last_line = self.thread_local.last_line

        if last_file == filename and last_line is not None:
            self.trace_data.add_arc(filename, cid, last_line, lineno)

        self.thread_local.last_line = lineno
        self.thread_local.last_file = filename

    def _record_opcode(self, filename: str, code_id: int, current_lasti: int, cid: int) -> None:
        last_lasti = self.thread_local.last_lasti
        last_code_id = getattr(self.thread_local, 'last_code_id', None)

        if last_lasti is not None and self.thread_local.last_file == filename and last_code_id == code_id:
            self.trace_data.add_instruction_arc(filename, cid, code_id, last_lasti, current_lasti)

        self.thread_local.last_lasti = current_lasti
        self.thread_local.last_file = filename
        self.thread_local.last_code_id = code_id

    def is_traceable(self, filename: str) -> bool:
        """
        Check if a file should be traced, utilizing a high-speed cache.
        """
        if filename not in self._cache_traceable:
            self._cache_traceable[filename] = self._should_trace(filename)
        return self._cache_traceable[filename]

    def _should_trace(self, filename: str) -> bool:
        """
        Compatibility wrapper for C tracer which expects this method to exist on the engine.
        """
        norm_file = self.path_manager.canonicalize(filename)
        # ensure matching the directory boundary to avoid prefix collisions
        if not os.environ.get("MINICOV_SELF_MEASURE"):
            if norm_file == self._lib_root or norm_file.startswith(self._lib_root + os.sep):
                return False
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

        # ensure project root is in sys.path to support imports from root (like python -m)
        if self.project_root not in sys.path:
            sys.path.insert(0, self.project_root)

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

    def report(self, reporters: Optional[List[str]] = None) -> None:
        """
        Combine data from parallel runs and generate reports using all registered reporters.
        """
        self.combine_data()
        results = self.analyze()

        if reporters:
            import copy
            cfg = copy.copy(self.config)
            cfg.reporters = reporters
            manager = ReportManager(cfg)
            manager.generate(results, self.project_root)
        else:
            self.report_manager.generate(results, self.project_root)
