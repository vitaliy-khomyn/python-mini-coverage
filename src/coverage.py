import sys
import os
import ast
import collections


# --- 1. Shared Utilities ---

class SourceParser:
    """
    Responsible solely for File I/O and AST generation.
    Adheres to SRP: Only changes if AST parsing logic changes.
    """

    def parse_file(self, filename):
        try:
            with open(filename, 'r') as f:
                source = f.read()
            return ast.parse(source)
        except (SyntaxError, OSError):
            return None


# --- 2. Coverage Strategies ---

class CoverageMetric:
    """
    Interface for coverage criteria.
    """

    def get_name(self):
        raise NotImplementedError

    def get_possible_elements(self, ast_tree):
        """
        Static Analysis: What *could* happen?
        """
        raise NotImplementedError

    def calculate_stats(self, possible_elements, executed_data):
        """
        Dynamic Analysis: What *did* happen?
        Returns: (percentage, missing_elements)
        """
        if not possible_elements:
            return 0.0, set()

        # Intersection logic is common for set-based coverage
        hit = possible_elements.intersection(executed_data)
        missing = possible_elements - hit
        pct = (len(hit) / len(possible_elements)) * 100
        return pct, missing


class StatementCoverage(CoverageMetric):
    def get_name(self):
        return "Statement"

    def get_possible_elements(self, ast_tree):
        """
        Returns a set of line numbers that contain executable statements.
        """
        executable_lines = set()
        for node in ast.walk(ast_tree):
            if isinstance(node, ast.stmt):
                # Ignore docstrings/constants
                if isinstance(node, ast.Expr) and isinstance(node.value, (ast.Str, ast.Constant)):
                    continue
                if hasattr(node, 'lineno'):
                    executable_lines.add(node.lineno)
        return executable_lines


class BranchCoverage(CoverageMetric):
    def get_name(self):
        return "Branch"

    def get_possible_elements(self, ast_tree):
        """
        Returns a set of arcs (start_line, end_line) representing possible jumps.
        """
        arcs = set()
        for node in ast.walk(ast_tree):
            # We currently only analyze IF statements for branching
            if isinstance(node, ast.If):
                self._analyze_if_branches(node, arcs)
        return arcs

    def _analyze_if_branches(self, node, arcs):
        start = node.lineno

        # 1. True Path
        if node.body:
            arcs.add((start, node.body[0].lineno))

        # 2. False Path
        if node.orelse:
            arcs.add((start, node.orelse[0].lineno))
        else:
            # Fallthrough (Implicit Else)
            # This requires context about the next sibling, which is hard in standard ast.walk.
            # For this MVP refactor, we acknowledge this limitation or would need a custom walker.
            # To keep it runnable and simple, we skip complex fallthrough detection here
            # or we could require a NodeVisitor to track siblings.
            pass


# --- 3. Reporting ---

class ConsoleReporter:
    def print_report(self, results, project_root):
        """
        results: Dict { filename: { 'Statement': (pct, missing), 'Branch': (pct, missing) } }
        """
        print("\n" + "=" * 90)
        # Dynamic headers based on what keys are in the results
        headers = f"{'File':<25} | {'Stmt Cov':<9} | {'Branch Cov':<11} | {'Missing'}"
        print(headers)
        print("-" * 90)

        for filename in sorted(results.keys()):
            file_data = results[filename]

            # Unpack specific known metrics for specific column formatting
            stmt_pct, stmt_miss = file_data.get('Statement', (0, set()))
            branch_stats = file_data.get('Branch')

            self._print_row(filename, stmt_pct, stmt_miss, branch_stats, project_root)

        print("=" * 90)

    def _print_row(self, filename, stmt_pct, stmt_miss, branch_stats, project_root):
        rel_name = os.path.relpath(filename, project_root)

        # Format Missing Lines
        missing_list = sorted(list(stmt_miss))
        if not missing_list:
            miss_str = ""
        elif len(missing_list) < 8:
            miss_str = ", ".join(map(str, missing_list))
        else:
            miss_str = f"{len(missing_list)} lines"

        # Format Branch Stats
        if branch_stats:
            branch_pct, _ = branch_stats
            # Only show branch coverage if branches exist (possible > 0)
            # We check this by seeing if the 'possible' set was empty in calculation
            # Actually, simpler: if we calculated it, print it.
            if branch_stats[0] == 0 and not branch_stats[1]:
                # If 0% and no missing, implies no branches existed (0/0)
                branch_str = "N/A"
            else:
                branch_str = f"{branch_pct:>3.0f}%"
        else:
            branch_str = "N/A"

        print(f"{rel_name:<25} | {stmt_pct:>6.0f}% | {branch_str:>11} | {miss_str}")


# --- 4. Main Coordinator ---

class MiniCoverage:
    def __init__(self, project_root=None, excluded_files=None):
        self.project_root = os.path.abspath(project_root) if project_root else os.getcwd()

        # Data Collection (Raw Traces)
        self.trace_data = {
            'lines': collections.defaultdict(set),  # {filename: {lines}}
            'arcs': collections.defaultdict(set)  # {filename: {(from, to)}}
        }

        # Strategies
        self.parser = SourceParser()
        self.metrics = [StatementCoverage(), BranchCoverage()]
        self.reporter = ConsoleReporter()

        # Trace State
        self._cache_traceable = {}
        self.excluded_files = self._build_exclusion_set(excluded_files)
        self.last_line = None
        self.last_file = None

    def _build_exclusion_set(self, user_excludes):
        excludes = set()
        if user_excludes:
            for f in user_excludes:
                excludes.add(os.path.abspath(f))
        excludes.add(os.path.abspath(__file__))
        return excludes

    def trace_function(self, frame, event, arg):
        """
        Collects raw execution data.
        NOTE: We keep collection logic centralized here for performance.
        Splitting this into multiple callbacks would slow down execution significantly.
        """
        if event != 'line':
            return self.trace_function

        filename = frame.f_code.co_filename

        if filename not in self._cache_traceable:
            self._cache_traceable[filename] = self._should_trace(filename)

        if self._cache_traceable[filename]:
            lineno = frame.f_lineno

            # 1. Collect Line Data
            self.trace_data['lines'][filename].add(lineno)

            # 2. Collect Arc Data
            if self.last_file == filename and self.last_line is not None:
                self.trace_data['arcs'][filename].add((self.last_line, lineno))

            self.last_line = lineno
            self.last_file = filename
        else:
            self.last_line = None
            self.last_file = None

        return self.trace_function

    def _should_trace(self, filename):
        abs_path = os.path.abspath(filename)
        if not abs_path.startswith(self.project_root):
            return False
        if abs_path in self.excluded_files:
            return False
        return True

    def analyze(self):
        """
        Orchestrates the analysis by querying metrics.
        """
        full_results = {}

        # Analyze every file that was touched
        all_files = set(self.trace_data['lines'].keys()) | set(self.trace_data['arcs'].keys())

        for filename in all_files:
            ast_tree = self.parser.parse_file(filename)
            if not ast_tree:
                continue

            file_results = {}
            for metric in self.metrics:
                # 1. Static Analysis
                possible = metric.get_possible_elements(ast_tree)

                # 2. Fetch relevant dynamic data
                # Mapping metric type to data source (Simple mapping for now)
                if metric.get_name() == "Statement":
                    executed = self.trace_data['lines'][filename]
                elif metric.get_name() == "Branch":
                    executed = self.trace_data['arcs'][filename]
                else:
                    executed = set()

                # 3. Calculate
                stats = metric.calculate_stats(possible, executed)
                file_results[metric.get_name()] = stats

            full_results[filename] = file_results

        return full_results

    def run(self, script_path, script_args=None):
        abs_script_path = os.path.abspath(script_path)
        script_dir = os.path.dirname(abs_script_path)

        original_argv = sys.argv
        original_path = sys.path[:]

        sys.argv = [script_path] + (script_args if script_args else [])
        sys.path.insert(0, script_dir)

        try:
            with open(abs_script_path, 'rb') as f:
                code = compile(f.read(), abs_script_path, 'exec')

            sys.settrace(self.trace_function)

            exec_globals = {
                '__name__': '__main__',
                '__file__': abs_script_path,
                '__builtins__': __builtins__
            }
            exec(code, exec_globals)

        except SystemExit:
            pass
        except Exception as e:
            print(f"\n[!] Exception: {e}")
        finally:
            sys.settrace(None)
            sys.argv = original_argv
            sys.path = original_path

    def report(self):
        results = self.analyze()
        self.reporter.print_report(results, self.project_root)


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python coverage_tool_v3.py <script_to_run.py> [args...]")
        sys.exit(1)

    target = sys.argv[1]
    args = sys.argv[2:]

    cov = MiniCoverage()
    cov.run(target, args)
    cov.report()