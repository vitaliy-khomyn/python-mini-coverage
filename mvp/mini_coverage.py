import sys
import os
import ast
import collections


class SourceAnalyzer:
    """
    Responsible for Static Analysis: parsing source code to determine
    what 'could' be executed (lines, and in future: branches, conditions).
    """

    def get_executable_lines(self, filename):
        """
        Parses python code to find lines that are actual code.
        """
        executable_lines = set()
        try:
            with open(filename, 'r') as f:
                source = f.read()
            tree = ast.parse(source)
        except (SyntaxError, OSError):
            return set()

        for node in ast.walk(tree):
            if self._is_executable_node(node):
                executable_lines.add(node.lineno)
        return executable_lines

    def _is_executable_node(self, node):
        """
        Determines if an AST node represents an executable statement.
        """
        if not isinstance(node, ast.stmt):
            return False

        # Ignore standalone docstrings or constant strings
        if isinstance(node, ast.Expr) and isinstance(node.value, (ast.Str, ast.Constant)):
            return False

        # Ensure the node actually has a line number
        if not hasattr(node, 'lineno'):
            return False

        return True


class ConsoleReporter:
    """
    Responsible for Presentation: formatting and displaying coverage results.
    """

    def print_report(self, coverage_stats, project_root):
        """
        Prints a summary report to stdout.
        coverage_stats: Dict of {filename: (percentage, missing_lines)}
        """
        print("\n" + "=" * 60)
        print(f"{'File':<25} | {'Cov%':<6} | {'Missing Lines'}")
        print("-" * 60)

        # Sort files for consistent output
        sorted_files = sorted(coverage_stats.keys())

        for filename in sorted_files:
            percentage, missing = coverage_stats[filename]
            self._print_file_report(filename, percentage, missing, project_root)

        print("=" * 60)

    def _print_file_report(self, filename, percentage, missing, project_root):
        rel_name = os.path.relpath(filename, project_root)

        # Compress missing lines for display
        missing_list = sorted(list(missing))
        if not missing_list:
            missing_str = ""
        elif len(missing_list) < 10:
            missing_str = ", ".join(map(str, missing_list))
        else:
            missing_str = f"{len(missing_list)} lines missed"

        print(f"{rel_name:<25} | {percentage:>5.0f}% | {missing_str}")


class MiniCoverage:
    def __init__(self, project_root=None, excluded_files=None):
        """
        Initialize the coverage tool.
        """
        self.project_root = os.path.abspath(project_root) if project_root else os.getcwd()
        self.executed_lines = collections.defaultdict(set)

        # Composition: Helpers for Analysis and Reporting
        self.analyzer = SourceAnalyzer()
        self.reporter = ConsoleReporter()

        self._cache_traceable = {}
        self.excluded_files = self._build_exclusion_set(excluded_files)

    def _build_exclusion_set(self, user_excludes):
        excludes = set()
        if user_excludes:
            for f in user_excludes:
                excludes.add(os.path.abspath(f))

        # Automatically exclude the tool itself
        excludes.add(os.path.abspath(__file__))
        return excludes

    def trace_function(self, frame, event, arg):
        """
        The system trace function called by Python.
        """
        if event != 'line':
            return self.trace_function

        filename = frame.f_code.co_filename

        # Optimization: Check cache first to avoid repetitive path operations in hot path
        if filename not in self._cache_traceable:
            self._cache_traceable[filename] = self._should_trace(filename)

        if self._cache_traceable[filename]:
            self.executed_lines[filename].add(frame.f_lineno)

        return self.trace_function

    def _should_trace(self, filename):
        """
        Determines if a file should be tracked based on root and exclusions.
        """
        abs_path = os.path.abspath(filename)

        # Rule 1: Must be inside the project root
        if not abs_path.startswith(self.project_root):
            return False

        # Rule 2: Must not be in the exclusion list
        if abs_path in self.excluded_files:
            return False

        return True

    def analyze_file(self, filename):
        """
        Calculates coverage statistics for a specific file.
        Returns: (coverage_percentage, set_of_missing_lines)
        """
        abs_path = os.path.abspath(filename)
        executed = self.executed_lines.get(abs_path, set())
        possible = self.analyzer.get_executable_lines(abs_path)

        missing = possible - executed

        if not possible:
            return 0.0, missing

        return (len(executed) / len(possible)) * 100, missing

    def run(self, script_path, script_args=None):
        """
        Runs the target script with coverage tracking.
        """
        abs_script_path = os.path.abspath(script_path)
        script_dir = os.path.dirname(abs_script_path)

        # Prepare environment
        original_argv = sys.argv
        original_path = sys.path[:]

        # Set sys.argv to [script_name, ...args]
        sys.argv = [script_path] + (script_args if script_args else [])
        sys.path.insert(0, script_dir)

        try:
            with open(abs_script_path, 'rb') as f:
                code = compile(f.read(), abs_script_path, 'exec')

            sys.settrace(self.trace_function)

            # Use a dictionary for globals to avoid polluting the tool's namespace
            exec_globals = {
                '__name__': '__main__',
                '__file__': abs_script_path,
                '__builtins__': __builtins__
            }

            exec(code, exec_globals)

        except SystemExit:
            pass  # Expected behavior for many scripts
        except Exception as e:
            print(f"\n[!] Exception during execution: {e}")
        finally:
            sys.settrace(None)
            sys.argv = original_argv
            sys.path = original_path

    def report(self):
        """
        Orchestrates the reporting process.
        """
        stats = {}
        # Calculate stats for all tracked files
        for filename in self.executed_lines.keys():
            stats[filename] = self.analyze_file(filename)

        self.reporter.print_report(stats, self.project_root)


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python mini_coverage.py <script_to_run.py> [args...]")
        sys.exit(1)

    target = sys.argv[1]
    args = sys.argv[2:]

    cov = MiniCoverage()
    cov.run(target, args)
    cov.report()
