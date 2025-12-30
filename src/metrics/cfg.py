import dis
import sys
import types
from typing import Set, Dict, List, Tuple


class ControlFlowGraph:
    """
    A representation of the Control Flow Graph (CFG) for a Python Code Object.

    Identifies Basic Blocks, computes edges (jumps/fallthroughs),
    exception handlers, and dominators.
    """

    def __init__(self, code: types.CodeType):
        self.code = code
        self.instructions = list(dis.get_instructions(code))
        self.offset_to_instr_idx = {instr.offset: i for i, instr in enumerate(self.instructions)}

        self.leaders = self._find_leaders()
        self.blocks = self._build_blocks()

        self.successors: Dict[int, Set[int]] = {b_start: set() for b_start, _ in self.blocks}
        self.predecessors: Dict[int, Set[int]] = {b_start: set() for b_start, _ in self.blocks}
        self._build_edges()

        self.dominators: Dict[int, Set[int]] = {}
        self._compute_dominators()

    def _find_leaders(self) -> Set[int]:
        """Find the starting offset of all basic blocks."""
        leaders = {0}

        for i, instr in enumerate(self.instructions):
            # target of any jump is a leader
            if instr.opcode in dis.hasjabs or instr.opcode in dis.hasjrel:
                target = int(instr.argval)
                leaders.add(target)

                # instruction following a jump is a leader
                if i + 1 < len(self.instructions):
                    leaders.add(self.instructions[i + 1].offset)

            # instruction following a return/raise is a leader (unreachable or new block)
            if instr.opname in ('RETURN_VALUE', 'RAISE_VARARGS', 'RETURN_CONST'):
                if i + 1 < len(self.instructions):
                    leaders.add(self.instructions[i + 1].offset)

        # exception handlers are leaders (Python 3.11+)
        if sys.version_info >= (3, 11) and hasattr(self.code, 'co_exceptiontable'):
            try:
                # dis.parse_exception_table returns (start, end, target, depth, lasti)
                for _, _, target, _, _ in dis.parse_exception_table(self.code):  # type: ignore
                    leaders.add(target)
            except Exception:
                pass

        return leaders

    def _build_blocks(self) -> List[Tuple[int, int]]:
        """Construct (start, end) ranges for basic blocks."""
        sorted_leaders = sorted(list(self.leaders))
        blocks = []

        for i, start in enumerate(sorted_leaders):
            if i + 1 < len(sorted_leaders):
                end_leader = sorted_leaders[i + 1]
                end_leader_idx = self.offset_to_instr_idx[end_leader]
                end_instr = self.instructions[end_leader_idx - 1]
            else:
                end_instr = self.instructions[-1]

            blocks.append((start, end_instr.offset))
        return blocks

    def _build_edges(self) -> None:
        """Populate successors and predecessors based on jumps and fallthroughs."""
        for start, end in self.blocks:
            end_idx = self.offset_to_instr_idx[end]
            end_instr = self.instructions[end_idx]

            targets = []

            # 1. jumps
            if end_instr.opcode in dis.hasjabs or end_instr.opcode in dis.hasjrel:
                targets.append(int(end_instr.argval))

            # 2. fallthrough: unconditional flow breakers
            is_unconditional = end_instr.opname in (
                'JUMP_ABSOLUTE',
                'JUMP_FORWARD',
                'JUMP_BACKWARD',
                'JUMP_BACKWARD_NO_INTERRUPT',
                'RETURN_VALUE',
                'RAISE_VARARGS',
                'RETURN_CONST'
            )
            # conditional jumps (POP_JUMP_IF_FALSE etc) also fall through
            if not is_unconditional:
                if end_idx + 1 < len(self.instructions):
                    targets.append(self.instructions[end_idx + 1].offset)

            # 3. exception Edges (simplified). TODO: exceptions cfg
            # in a real CFG, exceptions can occur at almost any instruction
            # here we map them if we parsed leaders from the exception table

            for t in targets:
                # Ensure target is a valid block start (it should be if leaders logic is correct)
                if t in self.successors:
                    self.successors[start].add(t)
                    self.predecessors[t].add(start)

    def _compute_dominators(self) -> None:
        """
        Compute dominators for each block using a standard iterative algorithm.
        Dom(n) = {n} U (Intersection of Dom(p) for all p in pred(n))
        """
        # initialize
        all_nodes = set(self.successors.keys())
        self.dominators = {node: all_nodes.copy() for node in all_nodes}

        # start node dominates itself
        start_node = 0
        if start_node in self.dominators:
            self.dominators[start_node] = {start_node}

        changed = True
        while changed:
            changed = False
            for node in all_nodes:
                if node == start_node:
                    continue

                preds = self.predecessors[node]
                if not preds:
                    continue

                # Intersection of all predecessors
                # Start with the first predecessor's dominators
                first_pred = next(iter(preds))
                new_dom = self.dominators[first_pred].copy()

                for p in preds:
                    new_dom &= self.dominators[p]

                new_dom.add(node)

                if new_dom != self.dominators[node]:
                    self.dominators[node] = new_dom
                    changed = True

    def get_jumps(self) -> Set[Tuple[int, int]]:
        """Return all edges as (source_instruction_offset, target_instruction_offset)"""
        jumps = set()
        for src, targets in self.successors.items():
            # src is the block start. We usually want the edge from the *end* instruction of the block
            # to the *start* instruction of the target block.
            # find the end instruction of the 'src' block
            block_end = next(end for s, end in self.blocks if s == src)

            for t in targets:
                jumps.add((block_end, t))
        return jumps
