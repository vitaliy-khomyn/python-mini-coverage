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

    def _evaluate_outcomes(self, code_obj: types.CodeType, missing_arcs: Set[Tuple[int, int, int]], executed_paths_data: Set[Tuple[int, Tuple[Tuple[int, int], ...]]]) -> Dict[int, Any]:
        return self.evaluate_mmcdc(code_obj, executed_paths_data)

    def evaluate_mmcdc(self, code_obj: types.CodeType, executed_paths_data: Set[Tuple[int, Tuple[Tuple[int, int], ...]]]) -> Dict[int, Any]:
        global_line_stats = collections.defaultdict(lambda: {'total': 0, 'missing': [], 'executed': [], 'conditions': 0})
        if not code_obj:
            return {}

        self._collect_line_ops(code_obj, global_line_stats)
        self._analyze_mmcdc(global_line_stats, executed_paths_data)

        return OutcomeFormatter.format_line_outcomes(global_line_stats, filter_redundant=False)

    def _analyze_mmcdc(self, global_line_stats: Dict[int, Any], executed_paths_data: Set[Tuple[int, Tuple[Tuple[int, int], ...]]]) -> None:
        """Extract executed paths and verify MMC/DC Independence Pairs."""
        for lineno, stats in global_line_stats.items():
            for decision in stats.get('decisions', []):
                ops = decision['ops']
                if not ops:
                    continue

                executed_paths = BooleanVectorEvaluator.extract_executed_paths(ops, executed_paths_data)

                decision['missing'] = []
                decision['executed'] = [{'vector': list(p), 'result': out} for p, out in executed_paths]
                decision['conditions'] = len(ops)
                decision['total_possible'] = len(ops)

                decision['missing'].extend(BooleanVectorEvaluator.find_missing_mmcdc_pairs(ops, executed_paths, decision.get('condition_names')))
