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
        possible_by_line = collections.defaultdict(list)
        executed_by_line = collections.defaultdict(list)

        for start, end in stats.get('missing', set()):
            missing_branches[start].append(end)
        for start, end in stats.get('possible', set()):
            possible_by_line[start].append(end)
        for start, end in stats.get('executed', set()):
            executed_by_line[start].append(end)

        for start, targets in missing_branches.items():
            targets_html = ", ".join(f'<a href="#L{t}">{t}</a>' for t in sorted(targets))
            poss = len(possible_by_line[start])
            exe = len(executed_by_line[start])
            annotations[start].append(f"<strong>Branch Coverage: {exe}/{poss}</strong><br>Missed branch to: {targets_html}")
        return dict(annotations)


class ConditionFormatter(BaseFormatter):
    max_rows_display = 10
    metric_name = "Condition Coverage"

    def _render_executed_rows(self, cond_info: Dict[str, Any], conditions_count: int) -> str:
        rows = []
        executed_items = cond_info.get('executed', [])
        for i, item in enumerate(executed_items):
            if self.max_rows_display and i >= self.max_rows_display and len(executed_items) > self.max_rows_display + 1:
                remaining = len(executed_items) - self.max_rows_display
                rows.append(f"<tr class='hit'><td colspan='{conditions_count + 1}' style='text-align: center; font-style: italic; color: #6c757d; background-color: #f8f9fa;'>... and {remaining} more executed combinations</td></tr>")
                break
            vector_html = "".join([f"<td>{html.escape(str(v))}</td>" for v in item['vector']])
            result_html = f"<td>{html.escape(str(item['result']))}</td>"
            rows.append(f"<tr class='hit'>{vector_html}{result_html}</tr>")
        return "".join(rows)

    def _render_missing_rows(self, cond_info: Dict[str, Any], conditions_count: int) -> str:
        rows = []
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
        return "".join(rows)

    def _render_table(self, cond_info: Dict[str, Any], conditions_count: int, condition_names: List[str]) -> str:
        header_cols = "".join([f"<th>{html.escape(condition_names[i] if i < len(condition_names) else f'Implicit Jump {i + 1 - len(condition_names)}')}</th>" for i in range(conditions_count)])
        header_cols += "<th>Result</th>"
        header_row = f"<tr>{header_cols}</tr>"

        executed_html = self._render_executed_rows(cond_info, conditions_count)
        missing_html = self._render_missing_rows(cond_info, conditions_count)
        return f"<strong>{self.metric_name}: {cond_info['ratio']}</strong><table class='condition-table'><tbody>{header_row}{executed_html}{missing_html}</tbody></table>"

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

                    table = self._render_table(cond_info, conditions_count, condition_names)
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
    metric_name = "MMC/DC Coverage"

    def _format_suggestion(self, suggestion: Dict[str, Any]) -> str:
        """Formats an MMC/DC suggestion pair into a nice HTML structure."""
        p1 = suggestion['p1']
        p2 = suggestion['p2']

        def _format_tile(data: Dict[str, Any]) -> str:
            vec_str = ", ".join(map(str, data['vector']))
            out_str = html.escape(str(data['outcome']))
            return f"""
            <div class="suggestion-tile">
                <div class="suggestion-vector">({vec_str})</div>
                <div class="suggestion-outcome">→ {out_str}</div>
            </div>
            """

        return f"""
        <div class="suggestion-pair" style="margin-top: 0;">
            <div class="suggestion-header">Suggested Pair:</div>
            {_format_tile(p1)}
            <div class="suggestion-conjunction">and</div>
            {_format_tile(p2)}
        </div>
        """

    def _render_table(self, cond_info: Dict[str, Any], conditions_count: int, condition_names: List[str]) -> str:
        header_cols = "".join([f"<th>{html.escape(condition_names[i] if i < len(condition_names) else f'Implicit Jump {i + 1 - len(condition_names)}')}</th>" for i in range(conditions_count)])
        header_cols += "<th>Result</th>"
        header_row = f"<tr>{header_cols}</tr>"

        executed_html = self._render_executed_rows(cond_info, conditions_count)
        executed_table = f"<div style='margin-bottom: 10px;'><div style='font-size: 0.9em; font-weight: bold; color: #495057;'>Executed Combinations:</div><table class='condition-table'><tbody>{header_row}{executed_html}</tbody></table></div>"

        missing_items = cond_info.get('missing', [])
        missing_by_idx = {item.get('condition_index', -1): item for item in missing_items}
        summary_rows = ["<tr><th>Condition</th><th>Proven</th><th>Details</th></tr>"]

        for i in range(conditions_count):
            name = condition_names[i] if i < len(condition_names) else f"Implicit Jump {i + 1 - len(condition_names)}"
            name_html = f"<code>{html.escape(name)}</code>"
            if i in missing_by_idx:
                item = missing_by_idx[i]
                proven_html = "<span style='color: #dc3545; font-weight: bold;'>False</span>"
                details_html = "<span style='color: #6c757d; font-style: italic;'>No independent pair possible (masked)</span>"
                if 'suggestion' in item:
                    details_html = self._format_suggestion(item['suggestion'])
                summary_rows.append(f"<tr class='miss'><td>{name_html}</td><td>{proven_html}</td><td>{details_html}</td></tr>")
            else:
                proven_html = "<span style='color: #28a745; font-weight: bold;'>True</span>"
                summary_rows.append(f"<tr class='hit'><td>{name_html}</td><td>{proven_html}</td><td style='color: #6c757d; font-style: italic;'>Independence proven</td></tr>")

        summary_table = f"<div><div style='font-size: 0.9em; font-weight: bold; color: #495057;'>Independence Summary:</div><table class='condition-table'><tbody>{''.join(summary_rows)}</tbody></table></div>"
        return f"<strong>{self.metric_name}: {cond_info['ratio']}</strong><hr class='annotation-divider'>{executed_table}{summary_table}"

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


class MCCFormatter(ConditionFormatter):
    metric_name = "MCC Coverage"

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


def _simple_count_formatter(name: str):
    class SimpleFormatter(BaseFormatter):
        def format_console(self, stats: Dict[str, Any]) -> str:
            missing = stats.get('missing', set())
            return f"{len(missing)} {name}" if missing else ""
    return SimpleFormatter


class FunctionFormatter(_simple_count_formatter("funcs")):
    def format_html(self, stats: Dict[str, Any]) -> Dict[int, List[str]]:
        return {def_line: [f"<strong>Function '{html.escape(name)}' was not called</strong>"] for name, def_line, _ in stats.get('missing', set())}


class LoopFormatter(_simple_count_formatter("loop paths")):
    def format_html(self, stats: Dict[str, Any]) -> Dict[int, List[str]]:
        return {start: ["<strong>Missed loop path(s)</strong>"] for start, _ in stats.get('missing', set())}


class ClassFormatter(_simple_count_formatter("classes")):
    def format_html(self, stats: Dict[str, Any]) -> Dict[int, List[str]]:
        return {def_line: [f"<strong>Class '{html.escape(name)}' was not instantiated</strong>"] for name, def_line, _ in stats.get('missing', set())}


class CallSiteFormatter(_simple_count_formatter("calls")):
    def format_html(self, stats: Dict[str, Any]) -> Dict[int, List[str]]:
        calls_by_line = collections.defaultdict(list)
        for name, lineno in stats.get('missing', set()):
            calls_by_line[lineno].append(name)
        return {lineno: [f"<strong>Missed call to: {html.escape(', '.join(names))}</strong>"] for lineno, names in calls_by_line.items()}


class ExceptionFormatter(_simple_count_formatter("exceptions")):
    def format_html(self, stats: Dict[str, Any]) -> Dict[int, List[str]]:
        return {lineno: ["<strong>Missed exception handler</strong>"] for lineno in stats.get('missing', set())}


class ReturnFormatter(_simple_count_formatter("returns")):
    def format_html(self, stats: Dict[str, Any]) -> Dict[int, List[str]]:
        return {lineno: ["<strong>Missed return statement</strong>"] for lineno in stats.get('missing', set())}
