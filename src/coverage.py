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
import html


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
            return {
                'pct': 100.0,  # Empty file is technically "fully covered" or 0, convention 100
                'missing': set(),
                'executed': set(),
                'possible': set()
            }

        hit = possible_elements.intersection(executed_data)
        missing = possible_elements - hit
        pct = (len(hit) / len(possible_elements)) * 100

        return {
            'pct': pct,
            'missing': missing,
            'executed': hit,
            'possible': possible_elements
        }


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
        print("\n" + "=" * 100)
        headers = f"{'File':<25} | {'Stmt Cov':<9} | {'Branch Cov':<11} | {'Missing'}"
        print(headers)
        print("-" * 100)

        for filename in sorted(results.keys()):
            file_data = results[filename]
            stmt_data = file_data.get('Statement')
            branch_data = file_data.get('Branch')
            self._print_row(filename, stmt_data, branch_data, project_root)
        print("=" * 100)

    def _print_row(self, filename, stmt_data, branch_data, project_root):
        rel_name = os.path.relpath(filename, project_root)

        # Statement Stats
        stmt_pct = stmt_data['pct']
        stmt_miss = sorted(list(stmt_data['missing']))

        # Branch Stats
        branch_pct = 0
        branch_miss = []
        has_branches = False

        if branch_data:
            possible = branch_data['possible']
            if possible:
                has_branches = True
                branch_pct = branch_data['pct']
                branch_miss = sorted(list(branch_data['missing']))

        # Format Missing Column
        # We combine missing lines and missing branches into one column
        missing_items = []

        # 1. Missing Lines
        if stmt_miss:
            # Compress ranges (e.g., 1, 2, 3 -> 1-3)
            # For simplicity in this text report, we usually just list them
            # or truncated list.
            if len(stmt_miss) > 5:
                missing_items.append(f"L{stmt_miss[0]}..L{stmt_miss[-1]}")
            else:
                missing_items.append(f"Lines: {','.join(map(str, stmt_miss))}")

        # 2. Missing Branches
        if branch_miss:
            # Format arcs 10->12
            arcs_str = [f"{start}->{end}" for start, end in branch_miss]
            if len(arcs_str) > 3:
                missing_items.append(f"Branches: {len(arcs_str)} missed")
            else:
                missing_items.append(f"Br: {', '.join(arcs_str)}")

        miss_str = "; ".join(missing_items)
        if not miss_str:
            miss_str = ""

        # Format Branch Column
        if not has_branches:
            branch_str = "N/A"
        else:
            branch_str = f"{branch_pct:>3.0f}%"

        print(f"{rel_name:<25} | {stmt_pct:>6.0f}% | {branch_str:>11} | {miss_str}")


class HtmlReporter:
    """
    Generates a static HTML site with code highlighting.
    """

    def __init__(self, output_dir="htmlcov"):
        self.output_dir = output_dir

    def generate(self, results, project_root):
        if not os.path.exists(self.output_dir):
            os.makedirs(self.output_dir)

        print(f"Generating HTML report in {self.output_dir}...")

        self._generate_index(results, project_root)

        for filename, data in results.items():
            self._generate_file_report(filename, data, project_root)

    def _generate_index(self, results, project_root):
        # Calculate Aggregates
        total_stmts = 0
        total_miss = 0

        rows = []
        for filename in sorted(results.keys()):
            stmt = results[filename]['Statement']
            possible = len(stmt['possible'])
            miss = len(stmt['missing'])
            total_stmts += possible
            total_miss += miss

            pct = stmt['pct']

            rel_name = os.path.relpath(filename, project_root)
            file_html_link = f"{self._sanitize_filename(rel_name)}.html"

            rows.append(f"""
            <tr>
                <td><a href="{file_html_link}">{html.escape(rel_name)}</a></td>
                <td>{possible}</td>
                <td>{miss}</td>
                <td>{pct:.0f}%</td>
            </tr>
            """)

        total_pct = 100.0
        if total_stmts > 0:
            total_pct = ((total_stmts - total_miss) / total_stmts) * 100

        html_content = f"""
        <html>
        <head>
            <title>Coverage Report</title>
            <style>
                body {{ font-family: sans-serif; padding: 20px; }}
                table {{ border-collapse: collapse; width: 100%; }}
                th, td {{ border: 1px solid #ddd; padding: 8px; text-align: left; }}
                th {{ background-color: #f2f2f2; }}
                .header {{ margin-bottom: 20px; }}
            </style>
        </head>
        <body>
            <div class="header">
                <h1>Coverage Report</h1>
                <p>Total Coverage: <strong>{total_pct:.0f}%</strong></p>
            </div>
            <table>
                <thead>
                    <tr>
                        <th>File</th>
                        <th>Statements</th>
                        <th>Missed</th>
                        <th>Coverage</th>
                    </tr>
                </thead>
                <tbody>
                    {"".join(rows)}
                </tbody>
            </table>
        </body>
        </html>
        """

        with open(os.path.join(self.output_dir, "index.html"), "w") as f:
            f.write(html_content)

    def _generate_file_report(self, filename, data, project_root):
        rel_name = os.path.relpath(filename, project_root)
        out_name = f"{self._sanitize_filename(rel_name)}.html"

        # Prepare Data
        stmt_data = data.get('Statement')
        executed_lines = stmt_data['executed']
        missing_lines = stmt_data['missing']

        branch_data = data.get('Branch')
        missing_branches = collections.defaultdict(list)
        if branch_data:
            for start, end in branch_data['missing']:
                missing_branches[start].append(end)

        try:
            with open(filename, 'r', encoding='utf-8') as f:
                source_lines = f.readlines()
        except Exception:
            source_lines = ["Error reading source file."]

        code_html = []
        for i, line in enumerate(source_lines):
            lineno = i + 1
            css_class = ""
            annotation = ""

            if lineno in executed_lines:
                css_class = "hit"
            elif lineno in missing_lines:
                css_class = "miss"

            # Branch Annotations
            if lineno in missing_branches:
                targets = missing_branches[lineno]
                # If hit but missing branches, mark as partial
                if css_class == "hit":
                    css_class = "partial"

                targets_str = ", ".join(map(str, targets))
                annotation = f"<span class='annotate'>Missed branch to: {targets_str}</span>"

            line_content = html.escape(line.rstrip())
            code_html.append(f"""
            <div class="line {css_class}">
                <span class="lineno">{lineno}</span>
                <pre>{line_content}</pre>
                {annotation}
            </div>
            """)

        html_content = f"""
        <html>
        <head>
            <title>{html.escape(rel_name)} - Coverage</title>
            <style>
                body {{ font-family: monospace; }}
                .line {{ display: flex; }}
                .lineno {{ width: 50px; color: #999; border-right: 1px solid #ddd; padding-right: 10px; margin-right: 10px; text-align: right; user-select: none; }}
                pre {{ margin: 0; }}
                .hit {{ background-color: #dff0d8; }}
                .miss {{ background-color: #f2dede; }}
                .partial {{ background-color: #fcf8e3; }}
                .annotate {{ color: #a94442; font-size: 0.8em; margin-left: 20px; font-style: italic; }}
            </style>
        </head>
        <body>
            <h3>{html.escape(rel_name)}</h3>
            {"".join(code_html)}
        </body>
        </html>
        """

        with open(os.path.join(self.output_dir, out_name), "w") as f:
            f.write(html_content)

    def _sanitize_filename(self, path):
        return path.replace(os.sep, "_").replace(".", "_")


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
        self.html_reporter = HtmlReporter()

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
        self.html_reporter.generate(results, self.project_root)


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python coverage_tool_v3.py <script_to_run.py> [args...]")
        sys.exit(1)

    target = sys.argv[1]
    args = sys.argv[2:]

    cov = MiniCoverage()
    cov.run(target, args)
    cov.report()