import sys
import types
from typing import Any
from .base import BaseTracer


class SysMonitoringTracer(BaseTracer):
    """
    Tracer implementation using sys.monitoring (Python 3.12+).
    """
    def start(self) -> bool:
        try:
            tool_id = sys.monitoring.COVERAGE_ID
            sys.monitoring.use_tool_id(tool_id, "MiniCoverage")

            # register callbacks
            # monitor PY_START to filter files efficiently
            sys.monitoring.register_callback(tool_id, sys.monitoring.events.PY_START, self._monitor_py_start)
            sys.monitoring.register_callback(tool_id, sys.monitoring.events.PY_RESUME, self._monitor_py_resume)
            sys.monitoring.register_callback(tool_id, sys.monitoring.events.LINE, self._monitor_line)
            sys.monitoring.register_callback(tool_id, sys.monitoring.events.BRANCH, self._monitor_branch)

            # enable PY_START globally. Local events will be enabled in _monitor_py_start.
            sys.monitoring.set_events(tool_id, sys.monitoring.events.PY_START)
            return True

        except Exception as e:
            self.engine.logger.warning(f"sys.monitoring failed: {e}. Falling back to sys.settrace.")
            return False

    def stop(self) -> None:
        try:
            tool_id = sys.monitoring.COVERAGE_ID
            sys.monitoring.set_events(tool_id, 0)
            sys.monitoring.free_tool_id(tool_id)
        except Exception as e:
            self.engine.logger.debug(f"Error stopping sys.monitoring: {e}")

    def _monitor_py_start(self, code: types.CodeType, instruction_offset: int) -> Any:
        """
        sys.monitoring callback for PY_START.
        Determines if a code object should be traced.
        """
        filename = code.co_filename

        if filename not in self.engine._cache_traceable:
            self.engine._cache_traceable[filename] = self.engine.path_manager.should_trace(filename, self.engine.excluded_files)

        if self.engine._cache_traceable[filename]:
            # enable LINE and BRANCH events for this code object
            sys.monitoring.set_local_events(sys.monitoring.COVERAGE_ID, code,
                                            sys.monitoring.events.LINE | sys.monitoring.events.BRANCH | sys.monitoring.events.PY_RESUME)

            # clear history on function entry to prevent cross-function arcs
            if hasattr(self.engine.thread_local, 'last_line'):
                self.engine.thread_local.last_line = None
                self.engine.thread_local.last_lasti = None
        else:
            sys.monitoring.set_local_events(sys.monitoring.COVERAGE_ID, code, 0)

    def _monitor_py_resume(self, code: types.CodeType, instruction_offset: int) -> Any:
        """
        sys.monitoring callback for PY_RESUME.
        """
        # clear history on function resume to prevent cross-function arcs
        if hasattr(self.engine.thread_local, 'last_line'):
            self.engine.thread_local.last_line = None
            self.engine.thread_local.last_lasti = None
        return None

    def _monitor_line(self, code: types.CodeType, line_number: int) -> Any:
        """
        sys.monitoring callback for LINE events.
        """
        filename = code.co_filename
        cid = self.engine._get_current_context_id()

        self.engine._record_line(filename, line_number, cid)
        return None  # keep event enabled

    def _monitor_branch(self, code: types.CodeType, from_offset: int, to_offset: int) -> Any:
        filename = code.co_filename
        cid = self.engine._get_current_context_id()
        self.engine.trace_data.add_instruction_arc(filename, cid, from_offset, to_offset)
        return None
