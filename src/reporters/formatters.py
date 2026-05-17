import collections
import html

from typing import Dict, Any, List, Tuple


class BaseFormatter:
    """Base class for metric-specific report formatting."""
    def format_console(self, stats: Dict[str, Any]) -> str:
        return ""

    def format_html(self, stats: Dict[str, Any]) -> Dict[int, List[str]]:
        return {}

    def get_totals(self, stats: Dict[str, Any]) -> Tuple[int, int]:
        """Returns (total_possible, total_executed) for the metric."""
        if 'total_possible' in stats:
            poss = stats['total_possible']
            miss = stats.get('total_missing', 0)
            return poss, poss - miss
        else:
            poss = len(stats.get('possible', []))
            hit = len(stats.get('executed', []))
            return poss, hit


class StatementFormatter(BaseFormatter):
    def format_console(self, stats: Dict[str, Any]) -> str:
        missing = stats.get('missing', set())
        if not missing:
            return ""
        missing_list = sorted(list(missing))
        if len(missing_list) > 5:
            return f"L{missing_list[0]}..L{missing_list[-1]}"
        return f"Lines: {','.join(map(str, missing_list))}"


class BranchFormatter(BaseFormatter):
    def format_console(self, stats: Dict[str, Any]) -> str:
        missing = stats.get('missing', set())
        if not missing:
            return ""
        arcs_str = [f"{start}->{end}" for start, end in sorted(list(missing))]
        if len(arcs_str) > 3:
            return f"Branches: {len(arcs_str)} missed"
        return f"Br: {', '.join(arcs_str)}"

    def format_html(self, stats: Dict[str, Any]) -> Dict[int, List[str]]:
        annotations = collections.defaultdict(list)
        missing_branches = collections.defaultdict(list)
        for start, end in stats.get('missing', set()):
            missing_branches[start].append(end)
        for start, targets in missing_branches.items():
            targets_str = ", ".join(map(str, targets))
            annotations[start].append(f"Missed branch to: {targets_str}")
        return dict(annotations)


class ConditionFormatter(BaseFormatter):
    max_rows_display = 10

    def format_html(self, stats: Dict[str, Any]) -> Dict[int, List[str]]:
        annotations = collections.defaultdict(list)
        missing_outcomes = stats.get('missing_outcomes', {})
        for lineno, decisions in missing_outcomes.items():
            if isinstance(decisions, dict):
                decisions = [decisions]

            for cond_info in decisions:
                if 'ratio' in cond_info and cond_info.get('missing'):
                    conditions_count = cond_info.get('conditions', 0)
                    condition_names = cond_info.get('condition_names', [])
                    if conditions_count == 0:
                        continue

                    header_cols = ""
                    for i in range(conditions_count):
                        if i < len(condition_names):
                            name = condition_names[i]
                        else:
                            name = f"Implicit Jump {i + 1 - len(condition_names)}"
                        header_cols += f"<th>{html.escape(name)}</th>"
                    header_cols += "<th>Result</th>"
                    header_row = f"<tr>{header_cols}</tr>"

                    rows = [header_row]

                    executed_items = cond_info.get('executed', [])
                    for i, item in enumerate(executed_items):
                        if self.max_rows_display and i >= self.max_rows_display and len(executed_items) > self.max_rows_display + 1:
                            remaining = len(executed_items) - self.max_rows_display
                            rows.append(f"<tr class='hit'><td colspan='{conditions_count + 1}' style='text-align: center; font-style: italic; color: #6c757d; background-color: #f8f9fa;'>... and {remaining} more executed combinations</td></tr>")
                            break

                        vector_html = "".join([f"<td>{html.escape(str(v))}</td>" for v in item['vector']])
                        result_html = f"<td>{html.escape(str(item['result']))}</td>"
                        rows.append(f"<tr class='hit'>{vector_html}{result_html}</tr>")

                    missing_items = cond_info.get('missing', [])
                    for i, item in enumerate(missing_items):
                        if self.max_rows_display and i >= self.max_rows_display and len(missing_items) > self.max_rows_display + 1:
                            remaining = len(missing_items) - self.max_rows_display
                            rows.append(f"<tr class='miss'><td colspan='{conditions_count + 1}' style='text-align: center; font-style: italic; color: #6c757d; background-color: #f8f9fa;'>... and {remaining} more missed combinations</td></tr>")
                            break

                        if 'message' in item:
                            rows.append(f"<tr class='miss'><td colspan='{conditions_count + 1}'>{html.escape(item['message'])}</td></tr>")
                        else:
                            vector_html = "".join([f"<td>{html.escape(str(v))}</td>" for v in item['vector']])
                            result_html = f"<td>{html.escape(str(item.get('result', '-')))}</td>"
                            rows.append(f"<tr class='miss'>{vector_html}{result_html}</tr>")

                    table_rows = "".join(rows)
                    table = f"<strong>Condition Coverage: {cond_info['ratio']}</strong>" \
                            f"<table class='condition-table'><tbody>{table_rows}</tbody></table>"
                    annotations[lineno].append(table)
        return dict(annotations)

    def get_totals(self, stats: Dict[str, Any]) -> Tuple[int, int]:
        missing_outcomes = stats.get('missing_outcomes')
        if missing_outcomes is not None:
            tot_poss = 0
            tot_miss = 0
            for decisions in missing_outcomes.values():
                if isinstance(decisions, dict):
                    decisions = [decisions]
                for line_stats in decisions:
                    tot_poss += line_stats.get('total', 0)
                    tot_miss += len(line_stats.get('missing', []))
            return tot_poss, tot_poss - tot_miss
        return super().get_totals(stats)


class MMCDCFormatter(ConditionFormatter):
    max_rows_display = 20

    def format_console(self, stats: Dict[str, Any]) -> str:
        missing_outcomes = stats.get('missing_outcomes', {})
        count = 0
        for decisions in missing_outcomes.values():
            if isinstance(decisions, dict):
                decisions = [decisions]
            for d in decisions:
                count += len(d.get('missing', []))
        if count > 0:
            return f"{count} MMC/DC missed"
        return ""

    def format_html(self, stats: Dict[str, Any]) -> Dict[int, List[str]]:
        html_map = super().format_html(stats)
        # Rename the generic table header for MMC/DC specifically
        return {k: [v.replace("Condition Coverage", "MMC/DC Coverage") for v in vals] for k, vals in html_map.items()}


class MCCFormatter(ConditionFormatter):
    def format_console(self, stats: Dict[str, Any]) -> str:
        missing_outcomes = stats.get('missing_outcomes', {})
        count = 0
        for decisions in missing_outcomes.values():
            if isinstance(decisions, dict):
                decisions = [decisions]
            for d in decisions:
                count += len(d.get('missing', []))
        if count > 0:
            return f"{count} MCC paths missed"
        return ""

    def format_html(self, stats: Dict[str, Any]) -> Dict[int, List[str]]:
        html_map = super().format_html(stats)
        return {k: [v.replace("Condition Coverage", "MCC Coverage") for v in vals] for k, vals in html_map.items()}


def _simple_count_formatter(name: str):
    class SimpleFormatter(BaseFormatter):
        def format_console(self, stats: Dict[str, Any]) -> str:
            missing = stats.get('missing', set())
            return f"{len(missing)} {name}" if missing else ""
    return SimpleFormatter


class FunctionFormatter(_simple_count_formatter("funcs")):
    def format_html(self, stats: Dict[str, Any]) -> Dict[int, List[str]]:
        return {def_line: [f"Function '{html.escape(name)}' was not called"] for name, def_line, _ in stats.get('missing', set())}


class LoopFormatter(_simple_count_formatter("loop paths")):
    def format_html(self, stats: Dict[str, Any]) -> Dict[int, List[str]]:
        return {start: ["Missed loop path(s)"] for start, _ in stats.get('missing', set())}


class ClassFormatter(_simple_count_formatter("classes")):
    def format_html(self, stats: Dict[str, Any]) -> Dict[int, List[str]]:
        return {def_line: [f"Class '{html.escape(name)}' was not instantiated"] for name, def_line, _ in stats.get('missing', set())}


class CallSiteFormatter(_simple_count_formatter("calls")):
    def format_html(self, stats: Dict[str, Any]) -> Dict[int, List[str]]:
        calls_by_line = collections.defaultdict(list)
        for name, lineno in stats.get('missing', set()):
            calls_by_line[lineno].append(name)
        return {lineno: [f"Missed call to: {html.escape(', '.join(names))}"] for lineno, names in calls_by_line.items()}


class ExceptionFormatter(_simple_count_formatter("exceptions")):
    def format_html(self, stats: Dict[str, Any]) -> Dict[int, List[str]]:
        return {lineno: ["Missed exception handler"] for lineno in stats.get('missing', set())}


class ReturnFormatter(_simple_count_formatter("returns")):
    def format_html(self, stats: Dict[str, Any]) -> Dict[int, List[str]]:
        return {lineno: ["Missed return statement"] for lineno in stats.get('missing', set())}
