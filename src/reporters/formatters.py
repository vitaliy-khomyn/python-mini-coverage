import html
import collections
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
        if not missing: return ""
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
    def format_html(self, stats: Dict[str, Any]) -> Dict[int, List[str]]:
        annotations = collections.defaultdict(list)
        missing_outcomes = stats.get('missing_outcomes', {})
        for lineno, cond_info in missing_outcomes.items():
            if isinstance(cond_info, dict) and 'ratio' in cond_info and cond_info.get('missing'):
                rows = "".join([f"<tr><td>{html.escape(item.get('vector', str(item)))}</td></tr>" for item in cond_info['missing']])
                table = f"<strong>Condition Coverage: {cond_info['ratio']}</strong>" \
                        f"<table class='condition-table'><tbody>{rows}</tbody></table>"
                annotations[lineno].append(table)
        return dict(annotations)


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
