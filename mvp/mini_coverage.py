import sys
import os
import ast
import collections


class MiniCoverage:
    def __init__(self):
        # Stores {filename: {set_of_executed_line_numbers}}
        self.executed_lines = collections.defaultdict(set)
        self.project_root = os.getcwd()

    def trace_function(self, frame, event, arg):
        """
        The hook called by Python for every line executed.
        """
        if event != 'line':
            return self.trace_function

        co = frame.f_code
        filename = os.path.abspath(co.co_filename)

        # FILTERING:
        # 1. Only track files in the current project directory
        # 2. Don't track the coverage tool itself
        if (filename.startswith(self.project_root) and
                not filename.endswith("mini_coverage.py") and
                not filename.endswith("test_coverage.py")):  # Don't track the test runner
            self.executed_lines[filename].add(frame.f_lineno)

        return self.trace_function

    def get_executable_lines(self, filename):
        """
        Uses AST (Abstract Syntax Tree) to find lines that *could* be executed.
        This ignores comments, docstrings, and blank lines.
        """
        executable_lines = set()

        with open(filename, 'r') as f:
            source = f.read()

        try:
            tree = ast.parse(source)
        except SyntaxError:
            return set()

        # Walk the tree and find all statements
        for node in ast.walk(tree):
            # We only care about statements (assignments, calls, loops, etc.)
            if isinstance(node, (ast.stmt, ast.expr)):
                # Some nodes (like multi-line strings) might span lines;
                # usually we just care about the start line.
                if hasattr(node, 'lineno'):
                    executable_lines.add(node.lineno)

        # Remove class/func definitions from executable count (optional preference,
        # but standard tools usually count the def line as executable)
        return executable_lines

    def run(self, script_path):
        """
        Loads and executes the target script under the trace hook.
        """
        # 1. Prepare the environment to look like the script is running directly
        # Save original argv/path to restore later
        original_argv = sys.argv
        original_path = sys.path[:]

        sys.argv = [script_path] + sys.argv[2:]
        script_dir = os.path.dirname(os.path.abspath(script_path))
        sys.path.insert(0, script_dir)

        # 2. Read the code
        with open(script_path, 'rb') as f:
            code = compile(f.read(), script_path, 'exec')

        # 3. Start Tracing
        sys.settrace(self.trace_function)

        try:
            # 4. Execute (in a localized global scope)
            exec(code, {'__name__': '__main__', '__file__': script_path})
        except SystemExit:
            pass
        except Exception as e:
            print(f"\n[!] Script raised an exception: {e}")
        finally:
            # 5. Stop Tracing
            sys.settrace(None)
            # Restore environment
            sys.argv = original_argv
            sys.path = original_path

    def analyze_file(self, filename):
        """
        Helper to calculate stats for a single file.
        Returns: (coverage_percentage, set_of_missing_lines)
        """
        abs_path = os.path.abspath(filename)
        executed = self.executed_lines.get(abs_path, set())
        possible = self.get_executable_lines(abs_path)

        missing = possible - executed

        if not possible:
            return 0.0, missing

        return (len(executed) / len(possible)) * 100, missing

    def report(self):
        print("\n" + "=" * 40)
        print(f"{'File':<20} | {'Cov%':<6} | {'Missing Lines'}")
        print("-" * 40)

        for filename, executed in self.executed_lines.items():
            percentage, missing = self.analyze_file(filename)

            rel_name = os.path.basename(filename)
            missing_str = ",".join(map(str, sorted(missing))) if missing else "-"

            print(f"{rel_name:<20} | {percentage:>5.0f}% | {missing_str}")
        print("=" * 40)


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python mini_coverage.py <script_to_run.py> [args]")
        sys.exit(1)

    target_script = sys.argv[1]

    cov = MiniCoverage()
    cov.run(target_script)
    cov.report()