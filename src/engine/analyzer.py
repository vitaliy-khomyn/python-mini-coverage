import os
from collections import defaultdict
from typing import Dict, Any, Set, List
from .config import CoverageConfig


class Analyzer:
    """
    Responsible for analyzing collected trace data against static code analysis
    to calculate coverage metrics.
    """

    def __init__(self, parser: Any, metrics: List[Any], config: CoverageConfig, path_manager: Any, excluded_files: Set[str]) -> None:
        self.parser = parser
        self.metrics = metrics
        self.config = config
        self.path_manager = path_manager
        self.excluded_files = excluded_files

    def _map_raw_files(self, trace_data: Dict[str, Dict[Any, Any]]) -> Dict[str, List[str]]:
        """Identify all unique files by normalized path to handle duplicates."""
        file_map = defaultdict(list)
        all_raw_files = (
            set(trace_data['lines'].keys()) |
            set(trace_data['arcs'].keys()) |
            set(trace_data['instruction_arcs'].keys())
        )
        for f in all_raw_files:
            file_map[self.path_manager.canonicalize(f)].append(f)
        return file_map

    def _aggregate_data_for_file(self, raw_files: List[str], trace_data: Dict[str, Any]) -> Dict[str, Set[Any]]:
        """Aggregates all trace data for a set of raw file paths that map to one canonical file."""
        aggregated = {'lines': set(), 'arcs': set(), 'instruction_arcs': set()}
        for key in aggregated.keys():
            for rf in raw_files:
                for ctx_data in trace_data[key].get(rf, {}).values():
                    aggregated[key].update(ctx_data)
        return aggregated

    def analyze(self, trace_data: Dict[str, Dict[Any, Any]]) -> Dict[str, Dict[str, Any]]:
        """
        Perform static analysis and compare with collected dynamic data.

        Args:
            trace_data: The collected trace data (lines, arcs, etc.)

        Returns:
            dict: A mapping of filenames to metric statistics.
        """
        full_results = {}

        file_map = self._map_raw_files(trace_data)

        exclude_patterns = self.config.exclude_lines

        for norm_file, raw_files in file_map.items():
            canonical_filename = raw_files[0]
            for rf in raw_files:
                if os.path.exists(rf):
                    canonical_filename = rf
                    break

            if not self.path_manager.should_trace(canonical_filename, self.excluded_files):
                continue

            aggregated_data = self._aggregate_data_for_file(raw_files, trace_data)

            ast_tree, ignored_lines = self.parser.parse_source(canonical_filename, exclude_patterns)
            if not ast_tree:
                continue

            code_obj = self.parser.compile_source(canonical_filename)

            file_results = {}
            for metric in self.metrics:
                static_source_type = metric.get_required_static_source()
                dynamic_data_key = metric.get_required_dynamic_data()

                static_source = ast_tree if static_source_type == 'ast' else code_obj
                dynamic_data = aggregated_data.get(dynamic_data_key, set())

                possible = metric.get_possible_elements(static_source, ignored_lines)  # type: ignore
                executed = dynamic_data

                stats = metric.calculate_stats(possible, executed)

                if metric.get_name() == "Condition" and hasattr(metric, 'map_missing_arcs'):
                    stats['missing_outcomes'] = metric.map_missing_arcs(code_obj, stats['missing'])

                file_results[metric.get_name()] = stats

            full_results[canonical_filename] = file_results

        return full_results
