from typing import List, Dict, Any, Set, Tuple


class BooleanVectorEvaluator:
    @staticmethod
    def get_branch_labels(opname: str) -> Tuple[str, str]:
        """Returns (jump_label, fallthrough_label) for a boolean opcode."""
        jump_val = "True" if "TRUE" in opname else "False"
        fall_val = "False" if jump_val == "True" else "True"
        return jump_val, fall_val

    @classmethod
    def _process_jump(cls, op_idx: int, vec: Tuple[str, ...], ops: List[Dict[str, Any]], jump_val: str, stack: List[Any], executed_paths: Set[Any]) -> None:
        new_vec = list(vec)
        new_vec[op_idx] = jump_val
        target = int(ops[op_idx]['instr'].argval)

        if target < ops[op_idx]['instr'].offset:
            # Backward jump (e.g. end of a while loop condition) is terminal for the condition evaluation chain
            next_idx = None
        else:
            next_idx = next((k for k in range(op_idx + 1, len(ops)) if ops[k]['instr'].offset >= target), None)

        if next_idx is not None:
            stack.append((next_idx, tuple(new_vec)))
        else:
            executed_paths.add((tuple(new_vec), jump_val))

    @classmethod
    def _process_fallthrough(cls, op_idx: int, vec: Tuple[str, ...], ops: List[Dict[str, Any]], fall_val: str, stack: List[Any], executed_paths: Set[Any]) -> None:
        new_vec = list(vec)
        new_vec[op_idx] = fall_val
        if op_idx == len(ops) - 1:
            executed_paths.add((tuple(new_vec), fall_val))
        else:
            stack.append((op_idx + 1, tuple(new_vec)))

    @staticmethod
    def extract_executed_paths(ops: List[Dict[str, Any]], executed_paths_data: Set[Tuple[int, Tuple[Tuple[int, int], ...]]]) -> Set[Tuple[Tuple[str, ...], str]]:
        """Extract the exact boolean vectors executed by tracing contiguous dynamic path sequences."""
        op_offsets = {op['instr'].offset: i for i, op in enumerate(ops)}
        executed_vectors = set()

        if not ops:
            return executed_vectors

        target_code_id = ops[0]['code_id']

        for code_id, path in executed_paths_data:
            if code_id != target_code_id:
                continue

            vec = ["-"] * len(ops)
            last_val = None
            has_ops = False

            for frm, to in path:
                if frm in op_offsets:
                    has_ops = True
                    op_idx = op_offsets[frm]
                    op_data = ops[op_idx]
                    jump_val, fall_val = BooleanVectorEvaluator.get_branch_labels(op_data['instr'].opname)

                    if to == int(op_data['instr'].argval):
                        vec[op_idx] = jump_val
                        last_val = jump_val
                    else:
                        vec[op_idx] = fall_val
                        last_val = fall_val

            if has_ops and last_val is not None:
                executed_vectors.add((tuple(vec), last_val))

        return executed_vectors

    @staticmethod
    def get_all_possible_paths(ops: List[Dict[str, Any]]) -> Set[Tuple[Tuple[str, ...], str]]:
        """Find all structurally possible condition vectors considering short-circuit evaluation."""
        possible_paths = set()
        stack = [(0, tuple(["-"] * len(ops)))]
        visited = set()

        while stack:
            op_idx, vec = stack.pop()
            if (op_idx, vec) in visited:
                continue
            visited.add((op_idx, vec))

            if op_idx >= len(ops):
                continue

            op_data = ops[op_idx]
            jump_val, fall_val = BooleanVectorEvaluator.get_branch_labels(op_data['instr'].opname)

            BooleanVectorEvaluator._process_jump(op_idx, vec, ops, jump_val, stack, possible_paths)
            if op_data['next_offset'] is not None:
                BooleanVectorEvaluator._process_fallthrough(op_idx, vec, ops, fall_val, stack, possible_paths)

        return possible_paths

    @staticmethod
    def find_missing_condition_arcs(ops: List[Dict[str, Any]], missing_arcs: Set[Tuple[int, int, int]]) -> List[Dict[str, Any]]:
        """Identify standard missing condition outcomes."""
        missing = []
        for i, op_data in enumerate(ops):
            instr, next_offset, code_id = op_data['instr'], op_data['next_offset'], op_data['code_id']
            jump_val, fall_val = BooleanVectorEvaluator.get_branch_labels(instr.opname)

            prefix = [BooleanVectorEvaluator.get_branch_labels(prev_op['instr'].opname)[1] for prev_op in ops[:i]]
            suffix_len = len(ops) - 1 - i

            # Check Jump Arc (Short-circuit path)
            target = int(instr.argval)
            if (code_id, instr.offset, target) in missing_arcs:
                vector = prefix + [jump_val] + ["-"] * suffix_len
                missing.append({'vector': vector, 'result': jump_val, 'terminal': True})

            # Check Fallthrough Arc (Continue path)
            if next_offset is not None and (code_id, instr.offset, next_offset) in missing_arcs:
                vector = prefix + [fall_val] + ["?"] * suffix_len
                missing.append({'vector': vector, 'result': '?', 'terminal': (i == len(ops) - 1)})
        return missing

    @staticmethod
    def find_missing_mmcdc_pairs(ops: List[Dict[str, Any]], executed_paths: Set[Tuple[Tuple[str, ...], str]]) -> List[Dict[str, Any]]:
        """Find variables that fail to prove their independent effect on the outcome (Masking MC/DC)."""
        missing = []
        possible_paths = BooleanVectorEvaluator.get_all_possible_paths(ops)

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
                suggestion = ""
                suggestion_found = False
                for p1, out1 in possible_paths:
                    for p2, out2 in possible_paths:
                        if out1 != out2 and p1[i] != p2[i] and p1[i] != "-" and p2[i] != "-":
                            if all(p1[j] == "-" or p2[j] == "-" or p1[j] == p2[j] for j in range(len(ops)) if i != j):
                                v1 = f"({', '.join(p1)})"
                                v2 = f"({', '.join(p2)})"
                                suggestion = f"Suggest pair: {v1} -> {out1} and {v2} -> {out2}"
                                suggestion_found = True
                                break
                    if suggestion_found:
                        break

                msg = f"Condition {i+1} independent effect not proven."
                if suggestion:
                    msg += f" {suggestion}"
                missing.append({'message': msg, 'terminal': True})
        return missing
