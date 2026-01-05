import os
from typing import Optional
from .base import BaseReporter, AnalysisResults, CoverageStats


class ConsoleReporter(BaseReporter):
    """
    Outputs coverage statistics to the standard output.
    """

    def generate(self, results: AnalysisResults, project_root: str) -> None:
        print("\n" + "=" * 115)
        headers = f"{'File':<40} | {'Stmt':>6} | {'Branch':>6} | {'Cond':>6} | {'Missing'}"
        print(headers)
        print("-" * 115)

        for filename in sorted(results.keys()):
            file_data = results[filename]
            stmt_data = file_data.get('Statement')
            branch_data = file_data.get('Branch')
            cond_data = file_data.get('Condition')

            if stmt_data:
                self._print_row(filename, stmt_data, branch_data, cond_data, project_root)
        print("=" * 115)

    def _print_row(self, filename: str, stmt_data: CoverageStats, branch_data: Optional[CoverageStats],
                   cond_data: Optional[CoverageStats], project_root: str) -> None:
        rel_name = os.path.relpath(filename, project_root)

        stmt_pct = stmt_data['pct']
        stmt_miss = sorted(list(stmt_data['missing']))

        branch_pct = 0
        branch_miss = []
        has_branches = False

        if branch_data:
            possible = branch_data['possible']
            if possible:
                has_branches = True
                branch_pct = branch_data['pct']
                branch_miss = sorted(list(branch_data['missing']))

        cond_str = "-"
        if cond_data:
            if cond_data.get('possible'):
                cond_str = f"{int(cond_data['pct'])}%"

        missing_items = []

        if stmt_miss:
            if len(stmt_miss) > 5:
                missing_items.append(f"L{stmt_miss[0]}..L{stmt_miss[-1]}")
            else:
                missing_items.append(f"Lines: {','.join(map(str, stmt_miss))}")

        if branch_miss:
            arcs_str = [f"{start}->{end}" for start, end in branch_miss]
            if len(arcs_str) > 3:
                missing_items.append(f"Branches: {len(arcs_str)} missed")
            else:
                missing_items.append(f"Br: {', '.join(arcs_str)}")

        miss_str = "; ".join(missing_items)
        if not miss_str:
            miss_str = ""

        if not has_branches:
            branch_str = "N/A"
        else:
            branch_str = f"{branch_pct:>3.0f}%"

        print(f"{rel_name:<40} | {stmt_pct:>5.0f}% | {branch_str:>6} | {cond_str:>6} | {miss_str}")
