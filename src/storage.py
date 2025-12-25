import os
import sqlite3
import glob
import uuid
from typing import Dict, Any, Callable, List, Tuple
from . import queries


class CoverageStorage:
    """
    Handles persistence of coverage data to SQLite.
    Responsible for initializing the DB, saving partial data, and merging results.
    """

    def __init__(self, data_file: str):
        self.data_file = data_file
        # Unique identifier for this process's partial file
        self.pid = os.getpid()
        self.uuid = uuid.uuid4().hex[:6]

    def _init_db(self, db_path: str) -> sqlite3.Connection:
        """
        Initialize the SQLite database schema.
        """
        conn = sqlite3.connect(db_path)
        cur = conn.cursor()

        cur.execute(queries.INIT_CONTEXTS)
        cur.execute(queries.INIT_DEFAULT_CONTEXT)
        cur.execute(queries.INIT_LINES)
        cur.execute(queries.INIT_ARCS)
        cur.execute(queries.INIT_INSTRUCTION_ARCS)

        conn.commit()
        return conn

    def save(self, trace_data: Dict[str, Dict[Any, Any]], context_cache: Dict[str, int]) -> None:
        """
        Dump in-memory coverage data to a unique SQLite file.
        """
        # Check if there is any data to save
        has_data = any(trace_data['lines'].values()) or any(trace_data['arcs'].values())
        if not has_data:
            return

        filename = f"{self.data_file}.{self.pid}.{self.uuid}"

        try:
            conn = self._init_db(filename)
            cur = conn.cursor()

            # Sync contexts
            ctx_data = [(cid, label) for label, cid in context_cache.items()]
            cur.executemany(queries.INSERT_CONTEXT, ctx_data)

            # Batch insert lines
            line_data = []
            for file, ctx_map in trace_data['lines'].items():
                for cid, lines in ctx_map.items():
                    for line in lines:
                        line_data.append((file, cid, line))
            cur.executemany(queries.INSERT_LINE, line_data)

            # Batch insert arcs
            arc_data = []
            for file, ctx_map in trace_data['arcs'].items():
                for cid, arcs in ctx_map.items():
                    for start, end in arcs:
                        arc_data.append((file, cid, start, end))
            cur.executemany(queries.INSERT_ARC, arc_data)

            # Batch insert instruction arcs
            instr_data = []
            for file, ctx_map in trace_data['instruction_arcs'].items():
                for cid, arcs in ctx_map.items():
                    for start, end in arcs:
                        instr_data.append((file, cid, start, end))
            cur.executemany(queries.INSERT_INSTRUCTION_ARC, instr_data)

            conn.commit()
            conn.close()
        except Exception as e:
            print(f"[!] Failed to save coverage data to DB: {e}")

    def combine(self, map_path_func: Callable[[str], str]) -> None:
        """
        Merge all partial coverage database files into the main database.
        """
        conn = self._init_db(self.data_file)
        # Register the path mapping function for use in SQL queries
        conn.create_function("remap_path", 1, map_path_func)
        cur = conn.cursor()

        pattern = f"{self.data_file}.*.*"

        for filename in glob.glob(pattern):
            try:
                alias = f"partial_{uuid.uuid4().hex}"
                cur.execute(f"ATTACH DATABASE ? AS {alias}", (filename,))

                # Copy new contexts from partial, ignoring existing labels
                cur.execute(queries.MERGE_CONTEXTS.format(alias=alias))

                # Merge lines (re-mapping IDs via join on label)
                cur.execute(queries.MERGE_LINES.format(alias=alias))

                # Merge arcs
                cur.execute(queries.MERGE_ARCS.format(alias=alias))

                # Merge instruction arcs
                cur.execute(queries.MERGE_INSTRUCTION_ARCS.format(alias=alias))

                conn.commit()
                cur.execute(f"DETACH DATABASE {alias}")
                os.remove(filename)
            except sqlite3.OperationalError:
                # Can happen if file is locked or corrupt
                pass
            except Exception as e:
                print(f"[!] Error combining {filename}: {e}")

        conn.close()

    def load_into(self, trace_data: Dict[str, Dict[Any, Any]]) -> None:
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
                trace_data['lines'][file][0].add(line)

            cur.execute(queries.SELECT_ARCS)
            for file, start, end in cur.fetchall():
                trace_data['arcs'][file][0].add((start, end))

            cur.execute(queries.SELECT_INSTRUCTION_ARCS)
            for file, start, end in cur.fetchall():
                trace_data['instruction_arcs'][file][0].add((start, end))

            conn.close()
        except sqlite3.OperationalError:
            pass