import glob
import logging
import os
import sqlite3
import uuid

from typing import Dict, Any, Callable

from . import queries
from .trace_data import TraceDataType


class CoverageStorage:
    """
    Handles persistence of coverage data to SQLite.
    Responsible for initializing the DB, saving partial data, and merging results.
    """

    def __init__(self, data_file: str):
        self.logger = logging.getLogger(__name__)
        self.data_file = data_file
        # unique identifier for this process's partial file
        self.pid = os.getpid()
        self.uuid = uuid.uuid4().hex[:6]

    def _init_db(self, db_path: str, timeout: float = 15.0) -> sqlite3.Connection:
        """
        Initialize the SQLite database schema.
        """
        conn = sqlite3.connect(db_path, timeout=timeout)
        cur = conn.cursor()

        cur.execute(queries.INIT_CONTEXTS)
        cur.execute(queries.INIT_DEFAULT_CONTEXT)
        cur.execute(queries.INIT_LINES)
        cur.execute(queries.INIT_ARCS)
        cur.execute(queries.INIT_INSTRUCTION_ARCS)

        conn.commit()
        return conn

    def save(self, trace_data: Dict[str, Dict[Any, Any]], context_cache: Dict[str, int], map_path_func: Callable[[str], str] = lambda x: x) -> None:
        """
        Dump in-memory coverage data to a unique SQLite file.
        """
        # check if there is any data to save
        has_data = any(trace_data[TraceDataType.LINES].values()) or any(trace_data[TraceDataType.ARCS].values())
        if not has_data:
            return

        filename = f"{self.data_file}.{self.pid}.{self.uuid}"

        try:
            conn = self._init_db(filename)
            cur = conn.cursor()

            # sync contexts
            ctx_data = [(cid, label) for label, cid in context_cache.items()]
            cur.executemany(queries.INSERT_CONTEXT, ctx_data)

            # batch insert lines
            line_data = []
            for file, ctx_map in trace_data[TraceDataType.LINES].items():
                for cid, lines in ctx_map.items():
                    for line in lines:
                        line_data.append((file, cid, line))
            cur.executemany(queries.INSERT_LINE, line_data)

            # batch insert arcs
            arc_data = []
            for file, ctx_map in trace_data[TraceDataType.ARCS].items():
                for cid, arcs in ctx_map.items():
                    for start, end in arcs:
                        arc_data.append((file, cid, start, end))
            cur.executemany(queries.INSERT_ARC, arc_data)

            # batch insert instruction arcs
            instr_data = []
            for file, ctx_map in trace_data[TraceDataType.INSTRUCTION_ARCS].items():
                for cid, arcs in ctx_map.items():
                    for code_id, start, end in arcs:
                        instr_data.append((file, cid, code_id, start, end))
            cur.executemany(queries.INSERT_INSTRUCTION_ARC, instr_data)

            conn.commit()
            conn.close()

            # Merge the partial file to the main database and delete it
            self._merge_partial(filename, map_path_func)

        except Exception as e:
            self.logger.error(f"Failed to save coverage data to DB: {e}")

    def _merge_partial(self, partial_filename: str, map_path_func: Callable[[str], str]) -> None:
        try:
            # use a timeout to handle concurrent writes to the main DB from multiple processes
            conn = self._init_db(self.data_file, timeout=15.0)
            conn.create_function("remap_path", 1, map_path_func)
            cur = conn.cursor()

            alias = f"partial_{uuid.uuid4().hex}"
            cur.execute(f"ATTACH DATABASE ? AS {alias}", (partial_filename,))

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
            conn.close()

            # since this process created the partial file, there is no lock contention
            try:
                os.remove(partial_filename)
            except OSError:
                pass
        except sqlite3.OperationalError as e:
            self.logger.debug(f"Skipping locked/corrupt partial file {partial_filename}: {e}")
        except Exception as e:
            self.logger.error(f"Error merging {partial_filename}: {e}")

    def combine(self, map_path_func: Callable[[str], str]) -> None:
        """
        Merge all leftover partial coverage database files into the main database.
        Most files should already be merged by the child processes themselves.
        """
        pattern = f"{self.data_file}.*.*"

        for filename in glob.glob(pattern):
            self._merge_partial(filename, map_path_func)

    def load_into(self, trace_data: Dict[str, Dict[Any, Any]], path_manager) -> None:
        """
        Populate in-memory trace data from the main database.
        Currently flattens data into the default context (0) for reporting.
        """
        if not os.path.exists(self.data_file):
            return

        try:
            conn = sqlite3.connect(self.data_file)
            cur = conn.cursor()

            cur.execute(queries.SELECT_LINES)
            for file, line in cur.fetchall():
                trace_data[TraceDataType.LINES][path_manager.canonicalize(file)][0].add(line)

            cur.execute(queries.SELECT_ARCS)
            for file, start, end in cur.fetchall():
                trace_data[TraceDataType.ARCS][path_manager.canonicalize(file)][0].add((start, end))

            cur.execute(queries.SELECT_INSTRUCTION_ARCS)
            for file, code_id, start, end in cur.fetchall():
                trace_data[TraceDataType.INSTRUCTION_ARCS][path_manager.canonicalize(file)][0].add((code_id, start, end))

            conn.close()
        except sqlite3.OperationalError as e:
            self.logger.debug(f"OperationalError loading {self.data_file}: {e}")
