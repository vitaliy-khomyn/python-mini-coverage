from typing import Any


class BaseTracer:
    """
    Abstract base class for tracing strategies.
    """
    def __init__(self, engine: Any):
        self.engine = engine

    def start(self) -> bool:
        """Start tracing. Return True if successful."""
        raise NotImplementedError

    def stop(self) -> None:
        """Stop tracing."""
        raise NotImplementedError
