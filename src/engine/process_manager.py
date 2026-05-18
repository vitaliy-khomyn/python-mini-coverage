import multiprocessing
import threading
from typing import Optional

_OriginalProcess = multiprocessing.Process
_config_local = threading.local()


class CoverageProcess(_OriginalProcess):
    _subprocess_setup = {"project_root": None, "config_file": None}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if hasattr(_config_local, "project_root"):
            self._cov_project_root = _config_local.project_root
            self._cov_config_file = _config_local.config_file
        else:
            self._cov_project_root = self._subprocess_setup["project_root"]
            self._cov_config_file = self._subprocess_setup["config_file"]

    def run(self) -> None:
        if self._cov_project_root:
            from .core import MiniCoverage
            cov = MiniCoverage(project_root=self._cov_project_root, config_file=self._cov_config_file)
            cov.start()
            try:
                super().run()
            finally:
                cov.stop()
        else:
            super().run()


class ProcessManager:
    @staticmethod
    def patch_multiprocessing(project_root: str, config_file: Optional[str]) -> None:
        CoverageProcess._subprocess_setup["project_root"] = project_root
        CoverageProcess._subprocess_setup["config_file"] = config_file

        if hasattr(multiprocessing, '_mini_coverage_patched'):
            return
        multiprocessing.Process = CoverageProcess
        multiprocessing._mini_coverage_patched = True  # type: ignore

    @staticmethod
    def set_thread_local(project_root: str, config_file: Optional[str]) -> None:
        _config_local.project_root = project_root
        _config_local.config_file = config_file

    @staticmethod
    def cleanup_thread_local() -> None:
        if hasattr(_config_local, "project_root"):
            del _config_local.project_root
        if hasattr(_config_local, "config_file"):
            del _config_local.config_file
