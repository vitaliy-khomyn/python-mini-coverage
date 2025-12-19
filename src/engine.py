import sys
import os
import collections
import threading
import multiprocessing
import pickle
import glob
import uuid
import fnmatch

# Relative imports assuming running as a package
from .source_parser import SourceParser
from .config_loader import ConfigLoader
from .metrics import StatementCoverage, BranchCoverage
from .reporters import ConsoleReporter, HtmlReporter


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
        # Ensure we exclude the tool's own source files
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