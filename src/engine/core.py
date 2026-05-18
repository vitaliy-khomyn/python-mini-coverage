import logging
import os
import shutil

from typing import Optional, List, Dict, Any, Set

from .analyzer import Analyzer
from .config import CoverageConfig
from .config_loader import ConfigLoader
from .path_manager import PathManager
from .report_manager import ReportManager
from .source_parser import SourceParser
from .storage import CoverageStorage
from .trace_data import TraceContainer

from ..metrics import StatementCoverage, BranchCoverage, ConditionCoverage, FunctionCoverage, LoopCoverage, ClassCoverage

from ..metrics.call_site import CallSiteCoverage
from ..metrics.exception import ExceptionCoverage
from ..metrics.mcc import MCCCoverage
from ..metrics.mmcdc import MMCDCCoverage
from ..metrics.return_coverage import ReturnCoverage

from .process_manager import ProcessManager
from .runner import ScriptRunner
from .tracer_controller import TracerController


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

        self.storage = CoverageStorage(self.config.data_file)
        self.parser = SourceParser()

        self._initialize_metrics()
        self._setup_exclusions()

        self.analyzer = Analyzer(self.parser, self.metrics, self.config, self.path_manager, self.excluded_files)
        self.report_manager = ReportManager(self.config)

        self.tracer_controller = TracerController(self)
        self.runner = ScriptRunner(self)

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
            MCCCoverage(),
        ]

    def _setup_exclusions(self) -> None:
        # ensure excluded files are also normalized
        self.excluded_files: Set[str] = set()

        # auto-exclude the tool's own source code to prevent self-instrumentation
        # get the 'src' directory (grandparent of this file)
        _src_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        self._lib_root = self.path_manager.canonicalize(_src_dir)
        self.excluded_files.add(self._lib_root)

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
        self.tracer_controller.switch_context(context_label)

    def save_data(self) -> None:
        """
        Dump the in-memory coverage data to a unique SQLite file via Storage Manager.
        """
        self.storage.save(self.trace_data, self.tracer_controller.context_cache, self.path_manager.map_path)

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

    def start(self) -> None:
        """
        Start coverage tracing.
        Uses sys.monitoring for Python 3.12+, otherwise falls back to sys.settrace.
        """
        ProcessManager.patch_multiprocessing(self.project_root, self.config_file)
        ProcessManager.set_thread_local(self.project_root, self.config_file)
        self.tracer_controller.start()

    def stop(self) -> None:
        """
        Stop coverage tracing and save data to disk.
        """
        ProcessManager.cleanup_thread_local()
        self.tracer_controller.stop()
        self.save_data()

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
        self.runner.run(script_path, script_args)

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
