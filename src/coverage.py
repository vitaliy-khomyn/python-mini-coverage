import sys
import os
import ast
import collections
import threading
import re
import configparser
import fnmatch
import multiprocessing
import pickle
import glob
import uuid


# --- 1. Shared Utilities ---

class SourceParser:
    """
    Responsible for File I/O, AST generation, and Pragma detection.
    """

    def parse_source(self, filename):
        """
        Returns tuple: (ast_tree, ignored_lines_set)
        """
        ignored_lines = set()
        try:
            with open(filename, 'r', encoding='utf-8') as f:
                source_lines = f.readlines()

            source_text = "".join(source_lines)
            tree = ast.parse(source_text)

            # Scan for pragmas
            # Pattern: # ... pragma: no cover ...
            pragma_pattern = re.compile(r'#.*pragma:\s*no\s*cover', re.IGNORECASE)

            for i, line in enumerate(source_lines):
                if pragma_pattern.search(line):
                    ignored_lines.add(i + 1)  # Lineno is 1-based in AST

            return tree, ignored_lines

        except (SyntaxError, OSError, UnicodeDecodeError):
            return None, set()


class ConfigLoader:
    """
    Responsible for loading configuration from files (.coveragerc, setup.cfg).
    """

    def load_config(self, project_root, config_file=None):
        config = {
            'omit': set()
        }

        # Default search paths if no specific file provided
        candidates = [config_file] if config_file else ['.coveragerc', 'setup.cfg', 'tox.ini']

        parser = configparser.ConfigParser()

        for cand in candidates:
            if not cand: continue
            path = os.path.join(project_root, cand)
            if os.path.exists(path):
                try:
                    parser.read(path)
                    # Check for [run] or [coverage:run] sections
                    section = None
                    if parser.has_section('run'):
                        section = 'run'
                    elif parser.has_section('coverage:run'):
                        section = 'coverage:run'

                    if section and parser.has_option(section, 'omit'):
                        omit_str = parser.get(section, 'omit')
                        # Handle multiline or comma-separated lists
                        for line in omit_str.replace(',', '\n').splitlines():
                            clean = line.strip()
                            if clean:
                                config['omit'].add(clean)

                    # Stop after finding the first valid config file
                    break
                except configparser.Error:
                    pass

        return config


# --- 2. Coverage Strategies ---

class CoverageMetric:
    def get_name(self):
        raise NotImplementedError

    def get_possible_elements(self, ast_tree, ignored_lines):
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

    def get_possible_elements(self, ast_tree, ignored_lines):
        executable_lines = set()
        for node in ast.walk(ast_tree):
            if isinstance(node, ast.stmt):
                # Check for Pragma exclusion
                if node.lineno in ignored_lines:
                    continue

                # Use ast.Constant for Python 3.8+ (replaces ast.Str/ast.Num)
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

    def get_possible_elements(self, ast_tree, ignored_lines):
        """
        Returns a set of arcs (start_line, end_line) representing possible jumps.
        Excludes arcs starting on ignored lines.
        """
        arcs = set()
        if hasattr(ast_tree, 'body'):
            self._scan_body(ast_tree.body, arcs, None, ignored_lines)
        return arcs

    def _scan_body(self, statements, arcs, next_lineno, ignored_lines):
        for i, node in enumerate(statements):
            # If the node is on an ignored line, skip analyzing its branches

            current_next = next_lineno
            if i + 1 < len(statements):
                current_next = statements[i + 1].lineno

            if hasattr(node, 'lineno') and node.lineno in ignored_lines:
                continue

            self._analyze_node(node, arcs, current_next, ignored_lines)

    def _analyze_node(self, node, arcs, next_lineno, ignored_lines):
        # Recursively scan children
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef, ast.Module)):
            self._scan_body(node.body, arcs, None, ignored_lines)
            return

        # 1. IF Statements
        if isinstance(node, ast.If):
            start = node.lineno

            # True Path
            if node.body:
                arcs.add((start, node.body[0].lineno))
                self._scan_body(node.body, arcs, next_lineno, ignored_lines)

            # False Path
            if node.orelse:
                arcs.add((start, node.orelse[0].lineno))
                self._scan_body(node.orelse, arcs, next_lineno, ignored_lines)
            else:
                if next_lineno:
                    arcs.add((start, next_lineno))

        # 2. Loops
        elif isinstance(node, (ast.For, ast.AsyncFor, ast.While)):
            start = node.lineno

            if node.body:
                arcs.add((start, node.body[0].lineno))
                self._scan_body(node.body, arcs, start, ignored_lines)

            if node.orelse:
                arcs.add((start, node.orelse[0].lineno))
                self._scan_body(node.orelse, arcs, next_lineno, ignored_lines)
            elif next_lineno:
                arcs.add((start, next_lineno))

        # 3. Match Statements
        elif hasattr(ast, 'Match') and isinstance(node, ast.Match):
            start = node.lineno
            has_wildcard = False
            for case in node.cases:
                if case.body:
                    arcs.add((start, case.body[0].lineno))
                    self._scan_body(case.body, arcs, next_lineno, ignored_lines)

                if isinstance(case.pattern, getattr(ast, 'MatchAs', type(None))) and case.pattern.pattern is None:
                    has_wildcard = True

            if not has_wildcard and next_lineno:
                arcs.add((start, next_lineno))

        # 4. Standard structural recursion
        else:
            if hasattr(node, 'body') and isinstance(node.body, list):
                self._scan_body(node.body, arcs, next_lineno, ignored_lines)
            if hasattr(node, 'orelse') and isinstance(node.orelse, list):
                self._scan_body(node.orelse, arcs, next_lineno, ignored_lines)
            if hasattr(node, 'finalbody') and isinstance(node.finalbody, list):
                self._scan_body(node.finalbody, arcs, next_lineno, ignored_lines)


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
    def __init__(self, project_root=None, config_file=None):
        self.project_root = os.path.abspath(project_root) if project_root else os.getcwd()
        self.config_file = config_file

        # Load Configuration
        self.config_loader = ConfigLoader()
        self.config = self.config_loader.load_config(self.project_root, config_file)

        self.trace_data = {
            'lines': collections.defaultdict(set),
            'arcs': collections.defaultdict(set)
        }

        self.parser = SourceParser()
        self.metrics = [StatementCoverage(), BranchCoverage()]
        self.reporter = ConsoleReporter()

        self._cache_traceable = {}
        self.excluded_files = {os.path.abspath(__file__)}
        self.thread_local = threading.local()

        # Multiprocessing Data Identifier
        self.pid = os.getpid()
        self.uuid = uuid.uuid4().hex[:6]

    def save_data(self):
        """Saves current coverage data to a unique file."""
        if not self.trace_data['lines'] and not self.trace_data['arcs']:
            return

        filename = f".coverage.{self.pid}.{self.uuid}"
        try:
            with open(filename, 'wb') as f:
                pickle.dump(self.trace_data, f)
        except Exception as e:
            print(f"[!] Failed to save coverage data: {e}")

    def combine_data(self):
        """Merges all .coverage.* files into the main trace_data."""
        pattern = ".coverage.*"
        for filename in glob.glob(pattern):
            try:
                # Avoid reading garbage or directory
                if not os.path.isfile(filename):
                    continue

                with open(filename, 'rb') as f:
                    data = pickle.load(f)

                    # Merge Lines
                    for file, lines in data.get('lines', {}).items():
                        self.trace_data['lines'][file].update(lines)

                    # Merge Arcs
                    for file, arcs in data.get('arcs', {}).items():
                        self.trace_data['arcs'][file].update(arcs)

                # Cleanup merged file
                os.remove(filename)
            except Exception:
                # If file is corrupt or locked, just skip
                pass

    def _patch_multiprocessing(self):
        """Monkey-patches multiprocessing.Process to enable coverage in child processes."""
        if hasattr(multiprocessing, '_mini_coverage_patched'):
            return

        OriginalProcess = multiprocessing.Process

        # Capture context for the child process
        project_root = self.project_root
        config_file = self.config_file

        class CoverageProcess(OriginalProcess):
            def run(self):
                # Bootstrap coverage in the child process
                cov = MiniCoverage(project_root=project_root, config_file=config_file)

                sys.settrace(cov.trace_function)
                threading.settrace(cov.trace_function)

                try:
                    super().run()
                finally:
                    sys.settrace(None)
                    threading.settrace(None)
                    cov.save_data()

        multiprocessing.Process = CoverageProcess
        multiprocessing._mini_coverage_patched = True

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

        # Check against configured 'omit' patterns
        rel_path = os.path.relpath(abs_path, self.project_root)
        for pattern in self.config['omit']:
            if fnmatch.fnmatch(rel_path, pattern):
                return False

        return True

    def analyze(self):
        full_results = {}
        all_files = set(self.trace_data['lines'].keys()) | set(self.trace_data['arcs'].keys())

        for filename in all_files:
            # Parse source AND ignored lines (pragmas)
            ast_tree, ignored_lines = self.parser.parse_source(filename)
            if not ast_tree:
                continue

            file_results = {}
            for metric in self.metrics:
                # Pass ignored lines to analysis
                possible = metric.get_possible_elements(ast_tree, ignored_lines)

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

            # Enable Multiprocessing Support
            self._patch_multiprocessing()

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
        # Merge data from any child processes before analyzing
        self.combine_data()

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