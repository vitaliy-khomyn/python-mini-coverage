import logging
import os
import sys
import threading
from typing import Optional, Dict, Any

try:
    import minicov_tracer
except ImportError:
    minicov_tracer = None

from ..tracing.sys_monitoring import SysMonitoringTracer
from ..tracing.sys_settrace import SysSetTraceTracer


class TraceState(threading.local):
    def __init__(self) -> None:
        self.last_line: Optional[int] = None
        self.last_file: Optional[str] = None
        self.last_lasti: Optional[int] = None
        self.last_code_id: Optional[int] = None


class TracerController:
    def __init__(self, engine: Any):
        self.engine = engine
        self.logger = logging.getLogger(__name__)
        self.trace_data = engine.trace_data

        self.current_context: str = "default"
        self.context_cache: Dict[str, int] = {"default": 0}
        self.reverse_context_cache: Dict[int, str] = {0: "default"}
        self._next_context_id: int = 1
        self._context_lock = threading.Lock()

        self._cache_traceable: Dict[str, bool] = {}
        self.thread_local = TraceState()

        self.c_tracer = None
        if minicov_tracer:
            try:
                self.c_tracer = minicov_tracer.Tracer(self)
                self.logger.info("Optimized C Tracer loaded.")
            except Exception as e:
                self.logger.warning(f"Failed to initialize C Tracer: {e}")

        self.sys_monitoring_tracer = SysMonitoringTracer(self)
        self.sys_settrace_tracer = SysSetTraceTracer(self, self.c_tracer)

    def switch_context(self, context_label: str) -> None:
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
        return self.context_cache.get(self.current_context, 0)

    def _start_new_frame(self) -> None:
        cid = self._get_current_context_id()
        self._flush_decision_path(cid)
        self.thread_local.last_line = None
        self.thread_local.last_lasti = None
        self.thread_local.last_file = None
        self.thread_local.last_code_id = None

    def _flush_decision_path(self, cid: int) -> None:
        path = getattr(self.thread_local, 'current_decision_path', None)
        last_file = getattr(self.thread_local, 'last_file', None)
        last_code_id = getattr(self.thread_local, 'last_code_id', None)

        if path and last_file and last_code_id is not None:
            self.trace_data.add_decision_path(last_file, cid, last_code_id, tuple(path))
            path.clear()

    def start(self) -> None:
        success = False
        if sys.version_info >= (3, 12):
            success = self.sys_monitoring_tracer.start()
        if not success:
            self.sys_settrace_tracer.start()

    def stop(self) -> None:
        if sys.version_info >= (3, 12):
            self.sys_monitoring_tracer.stop()
        self.sys_settrace_tracer.stop()
        cid = self._get_current_context_id()
        self._flush_decision_path(cid)

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
        if filename.startswith('<') and filename.endswith('>'):
            return False
        if filename not in self._cache_traceable:
            self._cache_traceable[filename] = self._should_trace(filename)
        return self._cache_traceable[filename]

    def _should_trace(self, filename: str) -> bool:
        if len(self._cache_traceable) > 4096:
            self._cache_traceable.clear()
        if filename.startswith('<') and filename.endswith('>'):
            return False
        norm_file = self.engine.path_manager.canonicalize(filename)
        if not os.environ.get("MINICOV_SELF_MEASURE"):
            if norm_file == self.engine._lib_root or norm_file.startswith(self.engine._lib_root + os.sep):
                return False
        return self.engine.path_manager.should_trace(filename, self.engine.excluded_files)
