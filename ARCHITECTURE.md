# **Project Architecture**

This document provides a technical breakdown of the MiniCoverage architecture. 
It is intended for developers who wish to understand the internal data flow, the database schema, or how to extend the tool.

## **System Overview**

The system follows a modular architecture based on the **Strategy Pattern** for metrics and the **Bridge Pattern** for storage and reporting. 
The core orchestration happens in the Engine, while the heavy lifting of data collection is offloaded to the Tracer (C extension).

### **Module Breakdown**

1. Engine (`src/engine.py`)  
   The central coordinator. It initializes the system, loads configuration, manages the active tracer backend (C vs Python vs `sys.monitoring`), and handles the lifecycle of a coverage session (start -> stop -> save). It owns the `trace_data` memory buffers.  
2. Storage (`src/storage.py`)  
   Handles all persistence. It abstracts away the SQLite implementation details. It is responsible for:  
   * Initializing the database schema.  
   * Saving in-memory data to unique process-specific files (to avoid locking contention).  
   * Merging (combining) multiple partial database files into a master `.coverage.db`.  
3. Metrics (`src/metrics/`)  
   This package defines what constitutes coverage. It uses a Strategy pattern where each metric class implements two methods: `get_possible_elements` (static analysis) and `calculate_stats` (dynamic analysis).  
   * `StatementCoverage`: Uses AST to find executable lines.  
   * `BranchCoverage`: Uses AST to find logical jumps.  
   * `ConditionCoverage`: Uses Bytecode analysis (CFG) to find boolean short-circuit operators for MC/DC.  
   * `ControlFlowGraph`: A utility that disassembles Python bytecode to build a graph of basic blocks and dominators.  
4. Reporters (`src/reporters/`)  
   Responsible for presenting the analyzed data.  
   * ConsoleReporter: Text tables.  
   * `HtmlReporter`: Static website generation.  
   * `XmlReporter`: Cobertura format for CI tools.  
   * `JsonReporter`: Raw data export.  
5. Source Parser (`src/source_parser.py`)  
   A facade for Python's ast and compile built-ins. It handles file I/O, encoding detection, and pragma (exclusion comment) stripping.  
6. Config Loader (`src/config_loader.py`)  
   Parses `pyproject.toml`, `.coveragerc`, and `setup.cfg`. It normalizes configuration options into a Python dictionary.  
7. Tracer (`src/tracer.c`)  
   A C-extension module that hooks into the CPython interpreter's `PyEval_SetTrace`. This is the "hot path" optimization.

## **Data Flow**

1. **Initialization**: MiniCoverage loads config and initializes Storage.  
2. **Startup**:  
   * If Python 3.12+: `sys.monitoring` is registered for LINE and BRANCH events.  
   * Else: sys.settrace is registered using the C-extension Tracer.  
   * multiprocessing is patched to ensure child processes start their own engines.  
3. **Execution**:  
   * As code runs, the Tracer receives events.  
   * It looks up the current context_id.  
   * It records data into thread-safe memory buffers:  
     * `lines[file][ctx] = set(integers)`  
     * `arcs[file][ctx] = set((int, int))`  
     * `instruction_arcs[file][ctx] = set((int, int))` (Bytecode offsets)  
4. **Teardown**:  
   * `stop()` is called.  
   * `save_data()` dumps the memory buffers to a uniquely named SQLite file (e.g., .coverage.db.1234.abcdef).  
5. **Reporting**:  
   * `combine_data()` scans for all partial DB files and merges them into .coverage.db using SQL INSERT OR IGNORE.  
   * `analyze()` re-reads the merged data and compares it against static analysis from Metrics.  
   * Reporters format the result.

## **Database Schema**

The persistence layer uses SQLite.

* **contexts**: Maps string labels (e.g., test names) to integer IDs to save space.  
* **lines**: Stores executed line numbers.  
  * Columns: `file_path`, `context_id`, `line_no`.  
* **arcs**: Stores line-to-line transitions.  
  * Columns: `file_path`, `context_id`, `start_line`, `end_line`.  
* **instruction_arcs**: Stores bytecode offset transitions (for MC/DC).  
  * Columns: `file_path`, `context_id`, `from_offset`, `to_offset`.

## **Design Decisions**

### **1. Persistence via SQLite**

SQLite was selected over flat file formats (such as JSON or pickle) to solve three critical issues inherent to coverage collection:

* **Concurrency:** In multiprocessing environments, multiple processes must write data simultaneously. SQLite handles file locking and concurrent access natively, whereas file-based approaches require complex manual locking mechanisms that are prone to race conditions (e.g., `WinError 32`).  
* **Memory Efficiency:** When combining data from thousands of test cases, loading a monolithic JSON blob into memory is inefficient. SQLite allows partial merges via SQL queries (`INSERT` OR `IGNORE`), keeping memory usage constant regardless of the dataset size.  
* **Partial Writes:** If a process crashes (e.g., `SEGFAULT`), flat files kept in memory are lost. SQLite allows for incremental journaling, increasing the chance of data recovery.

### **2. C-Extension Tracer Performance**

The default Python `sys.settrace` hook introduces significant overhead because it pauses the interpreter loop and creates a full Python stack frame object for every executed line. 
By implementing the tracer in C, this object creation overhead is bypassed.

* **Logic:** The C tracer stays within the CPython runtime. It accesses frame attributes (`f_lineno`, `f_lasti`) directly via C pointers rather than Python attribute lookups.  
* **Performance Gain:** Benchmarks typically show a reduction in runtime overhead from approximately **20x-50x** (pure Python trace) to **1.5x-2.5x** (C extension). This makes the tool viable for large production test suites where a 50x slowdown is unacceptable.

## **The C Tracer**

The file `src/tracer.c` implements the critical performance optimization.

### **Compilation**

If you modify src/tracer.c, you must recompile it for changes to take effect.  
Command:
```commandline
python setup.py build_ext --inplace
```

### **Logic**

The C tracer mirrors the Python trace_function. It hooks `PyTrace_LINE` and `PyTrace_OPCODE`. 
It interacts with the Python MiniCoverage instance to retrieve the `trace_data` dictionary and directly inserts values into the sets contained therein. 
It uses the CPython C-API to access frame attributes (`f_lineno`, `f_lasti`) directly, avoiding the overhead of creating Python frame objects.

## **Extension Guide**

**Adding a new Metric:**

1. Create a new class in `src/metrics/` inheriting from CoverageMetric.  
2. Implement `get_possible_elements` (analyze AST or bytecode to find what *should* happen).  
3. Implement `calculate_stats` (intersect possible with executed).  
4. Register the metric in `src/engine.py` inside `__init__`.

**Adding a new Reporter:**

1. Create a new class in `src/reporters/` inheriting from BaseReporter.  
2. Implement `generate(results, project_root)`.  
3. Register the reporter in `src/engine.py`.