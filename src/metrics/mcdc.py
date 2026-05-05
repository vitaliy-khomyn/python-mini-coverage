


import types
import collections
from typing import Set, Tuple, Dict, Any
from .condition import ConditionCoverage


class MMCDCCoverage(ConditionCoverage):
    """
    Masked Edge-Aggregated Modified Condition/Decision Coverage (MMC/DC).
    Evaluates whether each condition in a decision independently affects the outcome.
    """

    def get_name(self) -> str:
        return "MMC/DC"

    def evaluate_mmcdc(self, code_obj: types.CodeType, executed_arcs: Set[Tuple[int, int, int]]) -> Dict[int, Any]:
        global_line_stats = collections.defaultdict(lambda: {'total': 0, 'missing': []})
        if not code_obj:
            return {}

        self._collect_line_ops(code_obj, global_line_stats)
        self._analyze_mmcdc(global_line_stats, executed_arcs)

        result = {}
        for lineno, stats in global_line_stats.items():
            if stats['total'] == 0:
                continue
            covered = stats['total'] - len(stats['missing'])
            ratio = f"{covered}/{stats['total']}"
            result[lineno] = {
                'missing': stats['missing'],
                'ratio': ratio,
                'covered': covered,
                'total': stats['total']
            }
        return result

    def _analyze_mmcdc(self, global_line_stats: Dict[int, Any], executed_arcs: Set[Tuple[int, int, int]]) -> None:
        """Reconstruct executed paths and verify MMC/DC Independence Pairs."""
        for lineno, stats in global_line_stats.items():
            ops = stats.get('ops', [])
            if not ops:
                continue

            executed_paths = set()
            stack = [(0, tuple(["-"] * len(ops)))]
            visited = set()

            # 1. Reconstruct all executed condition vectors
            while stack:
                op_idx, vec = stack.pop()
                if (op_idx, vec) in visited:
                    continue
                visited.add((op_idx, vec))

                if op_idx >= len(ops):
                    continue

                op_data = ops[op_idx]
                instr, code_id = op_data['instr'], op_data['code_id']
                target = int(instr.argval)
                jump_val, fall_val = self._get_branch_labels(instr.opname)

                # Check Jump Taken
                if (code_id, instr.offset, target) in executed_arcs:
                    new_vec = list(vec)
                    new_vec[op_idx] = jump_val

                    next_idx = next((k for k in range(op_idx + 1, len(ops)) if ops[k]['instr'].offset >= target), None)
                    if next_idx is not None:
                        stack.append((next_idx, tuple(new_vec)))
                    else:
                        executed_paths.add((tuple(new_vec), jump_val))

                # Check Fallthrough
                next_offset = op_data['next_offset']
                if next_offset is not None and (code_id, instr.offset, next_offset) in executed_arcs:
                    new_vec = list(vec)
                    new_vec[op_idx] = fall_val
                    if op_idx == len(ops) - 1:
                        executed_paths.add((tuple(new_vec), fall_val))
                    else:
                        stack.append((op_idx + 1, tuple(new_vec)))

            # 2. Check Masking MMC/DC pairs for each condition
            stats['missing'] = []
            stats['total'] = len(ops)

            for i in range(len(ops)):
                pair_found = False
                for p1, out1 in executed_paths:
                    for p2, out2 in executed_paths:
                        # Look for differing outcomes and differing condition values
                        if out1 != out2 and p1[i] != p2[i] and p1[i] != "-" and p2[i] != "-":
                            # Check masking rule: all other evaluated conditions must be identical
                            if all(p1[j] == "-" or p2[j] == "-" or p1[j] == p2[j] for j in range(len(ops)) if i != j):
                                pair_found = True
                                break
                    if pair_found:
                        break

                if not pair_found:
                    stats['missing'].append({'vector': f"Condition {i+1} independent effect not proven", 'terminal': True})
