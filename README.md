# **MiniCoverage**

MiniCoverage is a modern code coverage tool designed for Python developers who need more than just line counts. While it started as a lightweight alternative to established frameworks, its primary goal is to serve as a platform for **further testing** and validation of new coverage metrics. It has evolved into a robust engine capable of advanced analysis features like Modified Condition/Decision Coverage (MC/DC) and multiprocessing support, all while maintaining a low performance overhead.  
The philosophy is simple: coverage tools should be invisible until needed, and when needed, accurate code execution data should be provided to validate new testing methodologies.

## **Overview**

At its core, MiniCoverage instruments Python code to track exactly which parts are executed during tests. Unlike simple tracers that only look at line numbers, MiniCoverage digs deeper into the Python bytecode. This enables verification that complex boolean logic was fully exercised and that the application behaves correctly even across multiple threads and processes.  
A hybrid approach to tracing is used. For maximum performance, the critical path of execution tracking is handled by a dedicated C extension. If that is not available, or if running on a newer Python version that supports it (3.12+), the tool automatically switches to the most efficient available method, such as sys.monitoring or a Python-based fallback.

## **Installation and Setup**

MiniCoverage is designed to be dropped into a project structure. Because a C extension is included for performance optimization, a C compiler is required on the system to build the optimized tracer.  
To set up, ensure the source code is in the project path. To enable the high-performance mode, the build command is run in the root directory:  
```commandline
python setup.py build_ext --inplace
```

If this step is skipped, the tool will still work perfectly fine using the pure Python implementation, though it may run slower on very large codebases.

## **Usage**

The tool is driven primarily through its command-line interface, which mirrors the workflow of standard Python execution.

### **Running Tests**

To measure coverage for a script, the run command is invoked. Instead of running python my\_script.py, the following command is used:  
```commandline
python -m src.main run my_script.py arg1 arg2
```

This executes the script exactly as Python would, but with instrumentation running in the background. The data collected during this run is safely stored in a local SQLite database, ensuring that even if the process crashes or is killed, the data collected up to that point is preserved.

### **Generating Reports**

Once tests have been run, human-readable reports can be generated. The report command aggregates all the data collected so far (even from multiple runs) and produces both a console summary and detailed files:  
python \-m src.main report

This will output a text summary to the terminal and generate a static HTML website in the htmlcov directory. htmlcov/index.html can be opened in any browser to explore the source code with color-coded highlighting showing exactly which lines and branches were missed.  

You can specify output formats using the `--format` flag:
```commandline
python -m src.main report --format console html xml json
```

For integration with CI/CD systems like Jenkins or Codecov, `xml` (Cobertura format) and `json` formats are available.

## **Configuration**

Sensible defaults are provided, but every project is different. MiniCoverage can be configured using standard configuration files like .coveragerc (INI format) or pyproject.toml.  
For example, to exclude specific files from being tracked or to define regex patterns for lines that should never be counted (like debug statements), a section can be added to the configuration file.  
**Using .coveragerc:**
```.editorconfig
[run]  
omit =   
    tests/*  
    setup.py

[report]  
exclude_lines =  
    def __repr__  
    if __name__ == "__main__":
```
**Using pyproject.toml:**
```.toml
[tool.coverage.run]  
branch = true  
omit = ["tests/*"]

[tool.coverage.report]  
exclude_lines = ["pragma: no cover"]
```
## **Key Features**

### ** MC/DC Support**

Most tools stop at Branch Coverage, which checks if an if statement went both True and False. MiniCoverage goes further by analyzing the bytecode to support Modified Condition/Decision Coverage. This means if a complex condition exists like if A and B, verification is performed to ensure that A and B were evaluated independently, ensuring robust testing for critical logic.

### **Concurrency Support**

Modern applications are rarely single-threaded. MiniCoverage automatically hooks into Python's threading model to capture execution in background threads. Multiprocessing is also supported, so if child processes are spawned, they will automatically bootstrap themselves and report coverage data back to the main database.

### **Dynamic Contexts**

To help understand *why* a line of code was executed, the engine supports dynamic contexts. This allows execution data to be tagged with a label, such as the name of the test currently running. This feature enables advanced workflows like Test Impact Analysis, where it can be determined exactly which tests need to be re-run when a specific file changes.  
