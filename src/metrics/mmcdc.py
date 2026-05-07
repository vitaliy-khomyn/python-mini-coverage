import collections
import types

from typing import Set, Tuple, Dict, Any

from .boolean_vector import BooleanVectorEvaluator
from .condition import ConditionCoverage, OutcomeFormatter


class MMCDCCoverage(ConditionCoverage):
    """
    Masked Edge-Aggregated Modified Condition/Decision Coverage (MMC/DC).
    Evaluates whether each condition in a decision independently affects the outcome.
    """

    def get_name(self) -> str:
        return "MMC/DC"

    def _evaluate_outcomes(self, code_obj: types.CodeType, missing_arcs: Set[Tuple[int, int, int]], executed_arcs: Set[Tuple[int, int, int]]) -> Dict[int, Any]:
        return self.evaluate_mmcdc(code_obj, executed_arcs)

    def evaluate_mmcdc(self, code_obj: types.CodeType, executed_arcs: Set[Tuple[int, int, int]]) -> Dict[int, Any]:
        global_line_stats = collections.defaultdict(lambda: {'total': 0, 'missing': [], 'executed': [], 'conditions': 0})
        if not code_obj:
            return {}

        self._collect_line_ops(code_obj, global_line_stats)
        self._analyze_mmcdc(global_line_stats, executed_arcs)

        return OutcomeFormatter.format_line_outcomes(global_line_stats, filter_redundant=False)

    def _analyze_mmcdc(self, global_line_stats: Dict[int, Any], executed_arcs: Set[Tuple[int, int, int]]) -> None:
        """Reconstruct executed paths and verify MMC/DC Independence Pairs."""
        for lineno, stats in global_line_stats.items():
            ops = stats.get('ops', [])
            if not ops:
                continue

            # 1. Reconstruct all executed condition vectors
            executed_paths = BooleanVectorEvaluator.reconstruct_executed_paths(ops, executed_arcs)

            # 2. Check Masking MMC/DC pairs for each condition
            stats['missing'] = []
            stats['executed'] = [{'vector': list(p), 'result': out} for p, out in executed_paths]
            stats['conditions'] = len(ops)
            stats['total'] = len(ops)

            stats['missing'].extend(BooleanVectorEvaluator.find_missing_mmcdc_pairs(ops, executed_paths))
