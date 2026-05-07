import collections
import types

from typing import Set, Tuple, Dict, Any

from .boolean_vector import BooleanVectorEvaluator
from .condition import ConditionCoverage, OutcomeFormatter


class MCCCoverage(ConditionCoverage):
    """
    Multiple Condition Coverage (MCC).
    Evaluates whether every structurally possible combination of conditions
    (respecting short-circuit evaluation paths) has been executed.
    """

    def get_name(self) -> str:
        return "MCC"

    def _evaluate_outcomes(self, code_obj: types.CodeType, missing_arcs: Set[Tuple[int, int, int]], executed_arcs: Set[Tuple[int, int, int]]) -> Dict[int, Any]:
        return self.evaluate_mcc(code_obj, executed_arcs)

    def evaluate_mcc(self, code_obj: types.CodeType, executed_arcs: Set[Tuple[int, int, int]]) -> Dict[int, Any]:
        global_line_stats = collections.defaultdict(lambda: {'total': 0, 'missing': [], 'executed': [], 'conditions': 0})
        if not code_obj:
            return {}

        self._collect_line_ops(code_obj, global_line_stats)
        self._analyze_mcc(global_line_stats, executed_arcs)

        return OutcomeFormatter.format_line_outcomes(global_line_stats, filter_redundant=False)

    def _analyze_mcc(self, global_line_stats: Dict[int, Any], executed_arcs: Set[Tuple[int, int, int]]) -> None:
        """Identify missing combinatorial paths."""
        for lineno, stats in global_line_stats.items():
            ops = stats.get('ops', [])
            if not ops:
                continue

            executed_paths = BooleanVectorEvaluator.reconstruct_executed_paths(ops, executed_arcs)
            possible_paths = BooleanVectorEvaluator.get_all_possible_paths(ops)
            missing_paths = possible_paths - executed_paths

            stats['missing'] = []
            for p, out in missing_paths:
                # By omitting the 'message' key, the formatter renders this as a clean table row.
                stats['missing'].append({'vector': list(p), 'result': out, 'terminal': True})

            stats['executed'] = [{'vector': list(p), 'result': out} for p, out in executed_paths]
            stats['conditions'] = len(ops)
            stats['total'] = len(possible_paths)
