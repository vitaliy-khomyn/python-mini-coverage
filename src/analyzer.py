import os
from collections import defaultdict
from typing import Dict, Any, Set


class Analyzer:
    """
    Responsible for analyzing collected trace data against static code analysis
    to calculate coverage metrics.
    """

    def __init__(self, parser, metrics, config: Dict[str, Any], path_manager, excluded_files: Set[str]):
        self.parser = parser
        self.metrics = metrics
        self.config = config
        self.path_manager = path_manager
        self.excluded_files = excluded_files

    def analyze(self, trace_data: Dict[str, Dict[Any, Any]]) -> Dict[str, Dict[str, Any]]:
        """
        Perform static analysis and compare with collected dynamic data.

        Args:
            trace_data: The collected trace data (lines, arcs, etc.)

        Returns:
            dict: A mapping of filenames to metric statistics.
        """
        full_results = {}

        # 1. identify all unique files by normalized path to handle duplicates (raw vs normalized)
        file_map = defaultdict(list)
        all_raw_files = (
            set(trace_data['lines'].keys()) | \
            set(trace_data['arcs'].keys()) | \
            set(trace_data['instruction_arcs'].keys())
        )

        for f in all_raw_files:
            norm = self.path_manager.canonicalize(f)
            file_map[norm].append(f)

        exclude_patterns = self.config.get('exclude_lines', set())

        for norm_file, raw_files in file_map.items():
            # 2. aggregate data from all raw aliases
            # use the first raw file as canonical, preferring existing ones
            canonical_filename = raw_files[0]
            for rf in raw_files:
                if os.path.exists(rf):
                    canonical_filename = rf
                    break

            if not self.path_manager.should_trace(canonical_filename, self.excluded_files):
                continue

            # aggregate lines
            aggregated_lines = set()
            for rf in raw_files:
                for ctx_lines in trace_data['lines'][rf].values():
                    aggregated_lines.update(ctx_lines)

            # aggregate arcs
            aggregated_arcs = set()
            for rf in raw_files:
                for ctx_arcs in trace_data['arcs'][rf].values():
                    aggregated_arcs.update(ctx_arcs)

            # aggregate instruction arcs
            aggregated_instr = set()
            for rf in raw_files:
                for ctx_instr in trace_data['instruction_arcs'][rf].values():
                    aggregated_instr.update(ctx_instr)

            # 3. parse and calculate metrics
            ast_tree, ignored_lines = self.parser.parse_source(canonical_filename, exclude_patterns)
            if not ast_tree:
                continue

            code_obj = self.parser.compile_source(canonical_filename)

            file_results = {}
            for metric in self.metrics:
                possible = set()
                executed = set()

                if metric.get_name() == "Statement":
                    possible = metric.get_possible_elements(ast_tree, ignored_lines)
                    executed = aggregated_lines
                elif metric.get_name() == "Branch":
                    possible = metric.get_possible_elements(ast_tree, ignored_lines)
                    executed = aggregated_arcs
                elif metric.get_name() == "Condition":
                    # condition coverage needs Code Object + Instruction Arcs
                    possible = metric.get_possible_elements(code_obj, ignored_lines)  # type: ignore
                    executed = aggregated_instr

                stats = metric.calculate_stats(possible, executed)
                file_results[metric.get_name()] = stats

            full_results[canonical_filename] = file_results

        return full_results
