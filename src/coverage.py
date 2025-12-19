import sys
import os
import ast
import collections
import threading


# --- 1. Shared Utilities ---

class SourceParser:
    """
    Responsible solely for File I/O and AST generation.
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
    def get_name(self):
        raise NotImplementedError

    def get_possible_elements(self, ast_tree):
        raise NotImplementedError

    def calculate_stats(self, possible_elements, executed_data):
        if not possible_elements:
            return 0.0, set()
        hit = possible_elements.intersection(executed_data)
        missing = possible_elements - hit
        pct = (len(hit) / len(possible_elements)) * 100
        return pct, missing


class StatementCoverage(CoverageMetric):
    def get_name(self):
        return "Statement"

    def get_possible_elements(self, ast_tree):
        executable_lines = set()
        for node in ast.walk(ast_tree):
            if isinstance(node, ast.stmt):
                # FIXED: Use ast.Constant for Python 3.8+ (replaces ast.Str/ast.Num)
                if isinstance(node, ast.Expr) and isinstance(node.value, ast.Constant):
                    # Check if it's a docstring (string constant)
                    if isinstance(node.value.value, str):
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
        Now uses a recursive scanner to track 'next statement' for fallthroughs.
        """
        arcs = set()
        # We start scanning the module body
        if hasattr(ast_tree, 'body'):
            self._scan_body(ast_tree.body, arcs)
        return arcs

    def _scan_body(self, statements, arcs, next_lineno=None):
        """
        Iterates over a list of statements, passing the 'next' context down.
        """
        for i, node in enumerate(statements):
            # Determine the fallthrough target for this node
            current_next = next_lineno
            if i + 1 < len(statements):
                current_next = statements[i + 1].lineno

            self._analyze_node(node, arcs, current_next)

    def _analyze_node(self, node, arcs, next_lineno):
        # Recursively scan children (Function defs, Classes, etc)
        # We generally treat function bodies as isolated blocks (next_lineno=None)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef, ast.Module)):
            self._scan_body(node.body, arcs, None)
            return

        # 1. IF Statements
        if isinstance(node, ast.If):
            start = node.lineno

            # True Path (Jump to Body)
            if node.body:
                arcs.add((start, node.body[0].lineno))
                # Recurse into body
                self._scan_body(node.body, arcs, next_lineno)

            # False Path (Else or Fallthrough)
            if node.orelse:
                arcs.add((start, node.orelse[0].lineno))
                # Recurse into else block
                self._scan_body(node.orelse, arcs, next_lineno)
            else:
                # Implicit Else: Jump to next statement
                if next_lineno:
                    arcs.add((start, next_lineno))

        # 2. Loops (For / AsyncFor / While)
        elif isinstance(node, (ast.For, ast.AsyncFor, ast.While)):
            start = node.lineno

            # Enter Loop (True Path)
            if node.body:
                arcs.add((start, node.body[0].lineno))
                self._scan_body(node.body, arcs, start)  # Loop loops back to start

            # Exit Loop (False/Skip Path)
            if node.orelse:
                arcs.add((start, node.orelse[0].lineno))
                self._scan_body(node.orelse, arcs, next_lineno)
            elif next_lineno:
                arcs.add((start, next_lineno))

        # 3. Match Statements (Python 3.10+)
        # We use getattr/hasattr to stay compatible with older Python versions
        elif hasattr(ast, 'Match') and isinstance(node, ast.Match):
            start = node.lineno

            # Match checks against cases
            has_wildcard = False
            for case in node.cases:
                # We assume the match statement jumps to the first line of a matching case body
                if case.body:
                    arcs.add((start, case.body[0].lineno))
                    self._scan_body(case.body, arcs, next_lineno)

                # Check for wildcard (default) case
                if isinstance(case.pattern, getattr(ast, 'MatchAs', type(None))) and case.pattern.pattern is None:
                    has_wildcard = True

            # If no wildcard exists, match can fall through to next statement
            if not has_wildcard and next_lineno:
                arcs.add((start, next_lineno))

        # 4. Standard structural recursion (Try, With, etc)
        else:
            # For other containers (Try, With), we just scan their bodies
            if hasattr(node, 'body') and isinstance(node.body, list):
                self._scan_body(node.body, arcs, next_lineno)
            if hasattr(node, 'orelse') and isinstance(node.orelse, list):
                self._scan_body(node.orelse, arcs, next_lineno)
            if hasattr(node, 'finalbody') and isinstance(node.finalbody, list):
                self._scan_body(node.finalbody, arcs, next_lineno)


# --- 3. Reporting ---

class ConsoleReporter:
    def print_report(self, results, project_root):
        print("\n" + "=" * 90)
        headers = f"{'File':<25} | {'Stmt Cov':<9} | {'Branch Cov':<11} | {'Missing'}"
        print(headers)
        print("-" * 90)

        for filename in sorted(results.keys()):
            file_data = results[filename]
            stmt_pct, stmt_miss = file_data.get('Statement', (0, set()))
            branch_stats = file_data.get('Branch')
            self._print_row(filename, stmt_pct, stmt_miss, branch_stats, project_root)
        print("=" * 90)

    def _print_row(self, filename, stmt_pct, stmt_miss, branch_stats, project_root):
        rel_name = os.path.relpath(filename, project_root)

        missing_list = sorted(list(stmt_miss))
        if not missing_list:
            miss_str = ""
        elif len(missing_list) < 8:
            miss_str = ", ".join(map(str, missing_list))
        else:
            miss_str = f"{len(missing_list)} lines"

        if branch_stats:
            branch_pct, _ = branch_stats
            if branch_stats[0] == 0 and not branch_stats[1]:
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

        self.trace_data = {
            'lines': collections.defaultdict(set),
            'arcs': collections.defaultdict(set)
        }

        self.parser = SourceParser()
        self.metrics = [StatementCoverage(), BranchCoverage()]
        self.reporter = ConsoleReporter()

        self._cache_traceable = {}
        self.excluded_files = self._build_exclusion_set(excluded_files)
        self.thread_local = threading.local()

    def _build_exclusion_set(self, user_excludes):
        excludes = set()
        if user_excludes:
            for f in user_excludes:
                excludes.add(os.path.abspath(f))
        excludes.add(os.path.abspath(__file__))
        return excludes

    def trace_function(self, frame, event, arg):
        if event != 'line':
            return self.trace_function

        filename = frame.f_code.co_filename

        if filename not in self._cache_traceable:
            self._cache_traceable[filename] = self._should_trace(filename)

        if self._cache_traceable[filename]:
            lineno = frame.f_lineno

            if not hasattr(self.thread_local, 'last_line'):
                self.thread_local.last_line = None
                self.thread_local.last_file = None

            self.trace_data['lines'][filename].add(lineno)

            last_file = self.thread_local.last_file
            last_line = self.thread_local.last_line

            if last_file == filename and last_line is not None:
                self.trace_data['arcs'][filename].add((last_line, lineno))

            self.thread_local.last_line = lineno
            self.thread_local.last_file = filename
        else:
            if hasattr(self.thread_local, 'last_line'):
                self.thread_local.last_line = None
                self.thread_local.last_file = None

        return self.trace_function

    def _should_trace(self, filename):
        abs_path = os.path.abspath(filename)
        if not abs_path.startswith(self.project_root):
            return False
        if abs_path in self.excluded_files:
            return False
        return True

    def analyze(self):
        full_results = {}
        all_files = set(self.trace_data['lines'].keys()) | set(self.trace_data['arcs'].keys())

        for filename in all_files:
            ast_tree = self.parser.parse_file(filename)
            if not ast_tree:
                continue

            file_results = {}
            for metric in self.metrics:
                possible = metric.get_possible_elements(ast_tree)

                if metric.get_name() == "Statement":
                    executed = self.trace_data['lines'][filename]
                elif metric.get_name() == "Branch":
                    executed = self.trace_data['arcs'][filename]
                else:
                    executed = set()

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
            threading.settrace(self.trace_function)

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
            threading.settrace(None)

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