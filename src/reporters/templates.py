"""
HTML templates and rendering helpers for the HTML reporter.
"""
from typing import List, Dict, Any, Optional


def render_index(headers: List[str], total_stats: List[Dict[str, Any]], rows: str) -> str:
    summary_items = []
    for stats in total_stats:
        summary_items.append(
            f'{stats["display"]}: <span class="{_get_css_class(stats["pct"])}">{stats["pct"]:.1f}% ({stats["ratio"]})</span>'
        )
    summary_html = " | ".join(summary_items)
    header_html = "".join([f'<th class="numeric sortable" onclick="sortTable({i+1}, this)">{h} <span></span></th>' for i, h in enumerate(headers)])
    return f"""
<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <title>MiniCoverage Report</title>
    <style>
        body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif; margin: 20px; color: #333; }}
        h1 {{ margin-bottom: 20px; }}
        .summary {{ margin-bottom: 30px; padding: 15px; background: #f8f9fa; border-radius: 5px; border: 1px solid #e9ecef; }}
        table {{ border-collapse: collapse; width: 100%; box-shadow: 0 1px 3px rgba(0,0,0,0.1); }}
        th, td {{ border: 1px solid #dee2e6; padding: 12px; text-align: left; }}
        th {{ background-color: #e9ecef; font-weight: 600; }}
        th.sortable {{ cursor: pointer; user-select: none; }}
        th.sortable:hover {{ background-color: #d1d8e0; }}
        tr:nth-child(even) {{ background-color: #f8f9fa; }}
        tr:hover {{ background-color: #f1f1f1; }}
        a {{ text-decoration: none; color: #007bff; }}
        a:hover {{ text-decoration: underline; }}
        .good {{ color: #28a745; font-weight: bold; }}
        .warn {{ color: #ffc107; font-weight: bold; }}
        .bad {{ color: #dc3545; font-weight: bold; }}
        .na {{ color: #adb5bd; font-style: italic; }}
        .numeric {{ text-align: right; font-family: monospace; }}
    </style>
    <script>
        let currentSortCol = -1;
        let sortDirection = 0;
        let originalRows = [];

        document.addEventListener("DOMContentLoaded", () => {{
            const tbody = document.querySelector("tbody");
            originalRows = Array.from(tbody.querySelectorAll("tr"));
        }});

        function sortTable(colIndex, headerElement) {{
            const tbody = document.querySelector("tbody");
            let rows = Array.from(tbody.querySelectorAll("tr"));

            if (currentSortCol === colIndex) {{
                sortDirection = (sortDirection + 1) % 3;
            }} else {{
                currentSortCol = colIndex;
                sortDirection = 1;
            }}

            document.querySelectorAll("th span").forEach(span => span.innerHTML = "");

            if (sortDirection === 0) {{
                tbody.innerHTML = "";
                originalRows.forEach(row => tbody.appendChild(row));
                currentSortCol = -1;
                return;
            }}

            headerElement.querySelector("span").innerHTML = sortDirection === 1 ? " ▲" : " ▼";

            rows.sort((a, b) => {{
                let valA = a.cells[colIndex].innerText.trim();
                let valB = b.cells[colIndex].innerText.trim();

                if (colIndex === 0) {{
                    return sortDirection === 1 ? valA.localeCompare(valB) : valB.localeCompare(valA);
                }} else {{
                    let numA = parseFloat(valA);
                    let numB = parseFloat(valB);
                    if (isNaN(numA)) numA = -1;
                    if (isNaN(numB)) numB = -1;

                    return sortDirection === 1 ? numA - numB : numB - numA;
                }}
            }});

            tbody.innerHTML = "";
            rows.forEach(row => tbody.appendChild(row));
        }}
    </script>
</head>
<body>
    <h1>Coverage Report</h1>
    <div class="summary">
        <strong>Total Coverage:</strong> {summary_html}
    </div>
    <table>
        <thead>
            <tr>
                <th class="sortable" onclick="sortTable(0, this)">File <span></span></th>
                {header_html}
            </tr>
        </thead>
        <tbody>
            {rows}
        </tbody>
    </table>
</body>
</html>
"""


def render_index_row(link: str, filename: str, metric_data_list: List[Dict[str, Any]]) -> str:
    cells_html = "".join([_render_cell(data) for data in metric_data_list])
    return f"""
    <tr>
        <td><a href="{link}">{filename}</a></td>
        {cells_html}
    </tr>
    """


def _render_cell(metric_data: Dict[str, Any]) -> str:
    if not metric_data or not metric_data.get('possible'):
        return '<td class="numeric na">N/A</td>'

    pct = metric_data.get('pct', 0)
    ratio = metric_data.get('ratio', "0/0")
    css = _get_css_class(pct)
    return f'<td class="numeric {css}">{pct:.0f}% <span style="font-size:0.8em; color:#555">({ratio})</span></td>'


def _get_css_class(pct: float) -> str:
    if pct >= 90:
        return "good"
    if pct >= 70:
        return "warn"
    return "bad"


def render_file(filename: str, code_html: str) -> str:
    return f"""
<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <title>Coverage: {filename}</title>
    <style>
        body {{ font-family: monospace; white-space: pre; margin: 0; padding: 0; }}
        .line {{ display: block; padding: 0 5px; clear: both; }}
        .lineno {{ color: #999; padding-right: 10px; user-select: none; }}
        .hit {{ background-color: #d4edda; }}
        .miss {{ background-color: #f8d7da; }}
        .partial {{ background-color: #fff3cd; }}
        .annotation-toggle {{ color: #721c24; background-color: #f8d7da; padding: 2px 5px; border-radius: 3px; font-size: 0.9em; cursor: pointer; float: right; margin-left: 20px; font-weight: bold; }}
        .annotation-toggle:hover {{ text-decoration: underline; }}
        .annotation-details {{
            display: none;
            margin-top: 5px;
            margin-bottom: 5px;
            padding: 5px 10px;
            background-color: #f8d7da;
            color: #721c24;
            border-left: 3px solid #721c24;
            font-family: sans-serif;
            white-space: normal;
            font-size: 0.9em;
            clear: both;
        }}
        .line.has-details {{ cursor: pointer; }}
        .condition-table {{ width: auto; border-collapse: collapse; font-size: 0.9em; margin-top: 5px; border: 1px solid #721c24; }}
        .condition-table th, .condition-table td {{ border: 1px solid #721c24; padding: 4px; text-align: left; }}
        .condition-table th {{ background-color: #e9ecef; }}
        .line.open .annotation-details {{ display: block; }}
        .annotation-list {{ margin: 0; padding-left: 20px; }}
    </style>
    <script>
        function toggleDetails(el, event) {{
            if (event && event.target.closest('.annotation-details')) return;
            var line = el.closest('.line');
            line.classList.toggle('open');
        }}
    </script>
</head>
<body>
    {code_html}
</body>
</html>
"""


def render_code_line(lineno: int, content: str, css_class: str, toggle_text: Optional[str] = None, details_html: Optional[str] = None) -> str:
    # content is already escaped
    extra_attrs = ""
    if details_html:
        css_class += " has-details"
        extra_attrs = ' onclick="toggleDetails(this, event)"'

    line_div = f'<div class="line {css_class}"{extra_attrs}>'
    line_div += f'<span class="lineno">{lineno}</span>'

    if toggle_text:
        line_div += f"<span class='annotation-toggle'>{toggle_text}</span>"

    line_div += content

    if details_html:
        line_div += f'<div class="annotation-details">{details_html}</div>'

    line_div += '</div>'
    return line_div
