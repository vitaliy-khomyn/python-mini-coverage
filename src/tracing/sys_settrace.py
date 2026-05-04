import sys
import threading
import types
from typing import Any, Optional
from .base import BaseTracer


class SysSetTraceTracer(BaseTracer):
    """
    Tracer implementation using sys.settrace (Python < 3.12 or fallback).
    """
    def __init__(self, engine: Any, c_tracer: Optional[Any] = None):
        super().__init__(engine)
        self.c_tracer = c_tracer

    def start(self) -> bool:
        tracer = self.c_tracer if self.c_tracer else self.trace_function
        sys.settrace(tracer)
        threading.settrace(tracer)
        return True

    def stop(self) -> None:
        sys.settrace(None)
        threading.settrace(None)

    def trace_function(self, frame: types.FrameType, event: str, arg: Any) -> Any:
        """
        The main system trace callback (Python fallback).
        """
        # enable opcode tracing for this frame
        if event == 'call':
            self.engine._start_new_frame()
            frame.f_trace_opcodes = True
            return self.trace_function

        if event == 'return':
            self.engine._start_new_frame()
            return self.trace_function

        if event not in ('line', 'opcode'):
            return self.trace_function

        filename = frame.f_code.co_filename

        if filename not in self.engine._cache_traceable:
            self.engine._cache_traceable[filename] = self.engine._should_trace(filename)

        if self.engine._cache_traceable[filename]:
            cid = self.engine._get_current_context_id()

            # 1. line trace
            if event == 'line':
                lineno = frame.f_lineno
                self.engine._record_line(filename, lineno, cid)

            # 2. opcode trace
            current_lasti = frame.f_lasti
            self.engine._record_opcode(filename, frame.f_code.co_firstlineno, current_lasti, cid)

        return self.trace_function
