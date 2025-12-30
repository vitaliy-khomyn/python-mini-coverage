"""
SQL queries used by the coverage engine.
"""

INIT_CONTEXTS = """
    CREATE TABLE IF NOT EXISTS contexts (
        id INTEGER PRIMARY KEY,
        label TEXT UNIQUE
    )
"""

INIT_DEFAULT_CONTEXT = "INSERT OR IGNORE INTO contexts (id, label) VALUES (0, 'default')"

INIT_LINES = """
    CREATE TABLE IF NOT EXISTS lines (
        file_path TEXT,
        context_id INTEGER,
        line_no INTEGER,
        PRIMARY KEY (file_path, context_id, line_no),
        FOREIGN KEY(context_id) REFERENCES contexts(id)
    )
"""

INIT_ARCS = """
    CREATE TABLE IF NOT EXISTS arcs (
        file_path TEXT,
        context_id INTEGER,
        start_line INTEGER,
        end_line INTEGER,
        PRIMARY KEY (file_path, context_id, start_line, end_line),
        FOREIGN KEY(context_id) REFERENCES contexts(id)
    )
"""

INIT_INSTRUCTION_ARCS = """
    CREATE TABLE IF NOT EXISTS instruction_arcs (
        file_path TEXT,
        context_id INTEGER,
        from_offset INTEGER,
        to_offset INTEGER,
        PRIMARY KEY (file_path, context_id, from_offset, to_offset),
        FOREIGN KEY(context_id) REFERENCES contexts(id)
    )
"""

INSERT_CONTEXT = "INSERT OR IGNORE INTO contexts (id, label) VALUES (?, ?)"
INSERT_LINE = "INSERT OR IGNORE INTO lines (file_path, context_id, line_no) VALUES (?, ?, ?)"
INSERT_ARC = "INSERT OR IGNORE INTO arcs (file_path, context_id, start_line, end_line) VALUES (?, ?, ?, ?)"
INSERT_INSTRUCTION_ARC = "INSERT OR IGNORE INTO instruction_arcs (file_path, context_id, from_offset, to_offset) VALUES (?, ?, ?, ?)"

# Dynamic queries (format strings)
MERGE_CONTEXTS = "INSERT OR IGNORE INTO contexts (label) SELECT label FROM {alias}.contexts"

# Updated to use remap_path function
MERGE_LINES = """
    INSERT OR IGNORE INTO lines (file_path, context_id, line_no)
    SELECT remap_path(l.file_path), main_c.id, l.line_no
    FROM {alias}.lines l
    JOIN {alias}.contexts partial_c ON l.context_id = partial_c.id
    JOIN contexts main_c ON partial_c.label = main_c.label
"""

MERGE_ARCS = """
    INSERT OR IGNORE INTO arcs (file_path, context_id, start_line, end_line)
    SELECT remap_path(a.file_path), main_c.id, a.start_line, a.end_line
    FROM {alias}.arcs a
    JOIN {alias}.contexts partial_c ON a.context_id = partial_c.id
    JOIN contexts main_c ON partial_c.label = main_c.label
"""

MERGE_INSTRUCTION_ARCS = """
    INSERT OR IGNORE INTO instruction_arcs (file_path, context_id, from_offset, to_offset)
    SELECT remap_path(a.file_path), main_c.id, a.from_offset, a.to_offset
    FROM {alias}.instruction_arcs a
    JOIN {alias}.contexts partial_c ON a.context_id = partial_c.id
    JOIN contexts main_c ON partial_c.label = main_c.label
"""

SELECT_LINES = "SELECT file_path, line_no FROM lines"
SELECT_ARCS = "SELECT file_path, start_line, end_line FROM arcs"
SELECT_INSTRUCTION_ARCS = "SELECT file_path, from_offset, to_offset FROM instruction_arcs"
