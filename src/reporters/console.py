import os
from typing import Optional
from .base import BaseReporter, AnalysisResults, CoverageStats


class ConsoleReporter(BaseReporter):
    """
    Outputs coverage statistics to the standard output.
    """

    def generate(self, results: AnalysisResults, project_root: str) -> None:
        print("\n" + "=" * 132)
        headers = f"{'File':<40} | {'Stmt':>6} | {'Branch':>6} | {'Cond':>6} | {'Func':>6} | {'Loop':>6} | {'Class':>6} | {'Missing'}"
        print(headers)
        print("-" * 132)

        for filename in sorted(results.keys()):
            file_data = results[filename]
            stmt_data = file_data.get('Statement')
            branch_data = file_data.get('Branch')
            cond_data = file_data.get('Condition')
            func_data = file_data.get('Function')
            loop_data = file_data.get('Loop')
            class_data = file_data.get('Class')

            if stmt_data:
                self._print_row(filename, stmt_data, branch_data, cond_data, func_data, loop_data, class_data, project_root)
        print("=" * 132)

    def _print_row(self, filename: str, stmt_data: CoverageStats, branch_data: Optional[CoverageStats],
                   cond_data: Optional[CoverageStats], func_data: Optional[CoverageStats],
                   loop_data: Optional[CoverageStats], class_data: Optional[CoverageStats],
                   project_root: str) -> None:
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

        func_str = "-"
        if func_data and func_data.get('possible'):
            func_str = f"{int(func_data['pct'])}%"

        loop_str = "-"
        if loop_data and loop_data.get('possible'):
            loop_str = f"{int(loop_data['pct'])}%"

        class_str = "-"
        if class_data and class_data.get('possible'):
            class_str = f"{int(class_data['pct'])}%"

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

        if func_data and func_data.get('missing'):
            missing_func_count = len(func_data['missing'])
            if missing_func_count > 0:
                missing_items.append(f"{missing_func_count} funcs")

        if loop_data and loop_data.get('missing'):
            missing_loop_count = len(loop_data['missing'])
            if missing_loop_count > 0:
                missing_items.append(f"{missing_loop_count} loop paths")

        if class_data and class_data.get('missing'):
            missing_class_count = len(class_data['missing'])
            if missing_class_count > 0:
                missing_items.append(f"{missing_class_count} classes")

        miss_str = "; ".join(missing_items)
        if not miss_str:
            miss_str = ""

        if not has_branches:
            branch_str = "N/A"
        else:
            branch_str = f"{branch_pct:>3.0f}%"

        print(f"{rel_name:<40} | {stmt_pct:>5.0f}% | {branch_str:>6} | {cond_str:>6} | {func_str:>6} | {loop_str:>6} | {class_str:>6} | {miss_str}")
