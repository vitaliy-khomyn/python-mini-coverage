"""
HTML templates and rendering helpers for the HTML reporter.
"""
from typing import List, Dict, Any, Optional


def render_index(headers: List[str], total_stats: List[Dict[str, Any]], rows: str) -> str:
    summary_items = []
    for stats in total_stats:
        summary_items.append(
            f'<div class="metric-card"><div class="title">{stats["display"]}</div><div class="value {_get_css_class(stats["pct"])}">{stats["pct"]:.1f}% <span class="ratio">({stats["ratio"]})</span></div></div>'
        )
    summary_html = "".join(summary_items)
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
        .summary {{ display: flex; flex-wrap: wrap; gap: 15px; margin-bottom: 30px; }}
        .metric-card {{ flex: 1; min-width: 150px; padding: 15px; background: #f8f9fa; border-radius: 8px; border: 1px solid #e9ecef; text-align: center; box-shadow: 0 2px 4px rgba(0,0,0,0.05); }}
        .metric-card .title {{ font-size: 0.85em; color: #6c757d; text-transform: uppercase; letter-spacing: 1px; margin-bottom: 10px; font-weight: 600; }}
        .metric-card .value {{ font-size: 1.6em; font-weight: bold; }}
        .metric-card .ratio {{ font-size: 0.5em; color: #adb5bd; font-weight: normal; }}
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
        {summary_html}
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
        body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif; margin: 0; padding: 0; background: #f8f9fa; }}
        .header {{ padding: 12px 20px; background: #fff; border-bottom: 1px solid #dee2e6; box-shadow: 0 1px 3px rgba(0,0,0,0.05); position: sticky; top: 0; z-index: 100; display: flex; align-items: center; gap: 15px; }}
        .header a {{ text-decoration: none; color: #495057; font-weight: 500; border: 1px solid #ced4da; padding: 6px 12px; border-radius: 4px; transition: all 0.2s; background: #f8f9fa; font-size: 0.9em; }}
        .header a:hover {{ background: #e9ecef; color: #212529; }}
        .header strong {{ font-family: monospace; font-size: 1.1em; color: #343a40; }}
        
        .code-container {{ background: #fff; margin: 20px; border-radius: 8px; border: 1px solid #dee2e6; box-shadow: 0 2px 5px rgba(0,0,0,0.05); overflow: hidden; }}
        .line {{ display: flex; align-items: stretch; font-family: 'SFMono-Regular', Consolas, 'Liberation Mono', Menlo, monospace; font-size: 14px; line-height: 1.6; border-bottom: 1px solid #f1f3f5; }}
        .line:last-child {{ border-bottom: none; }}
        
        .lineno {{ width: 50px; min-width: 50px; text-align: right; padding-right: 15px; color: #adb5bd; background: #f8f9fa; border-right: 1px solid #dee2e6; user-select: none; padding-top: 2px; padding-bottom: 2px; }}
        .code-content {{ flex: 1; padding-left: 15px; padding-top: 2px; padding-bottom: 2px; white-space: pre-wrap; word-break: break-all; position: relative; }}
        
        .hit {{ background-color: #e6f4ea; }}
        .miss {{ background-color: #fce4e4; }}
        .partial {{ background-color: #fff8e1; }}
        
        .hit .lineno {{ background-color: #d4edda; color: #155724; border-right-color: #c3e6cb; }}
        .miss .lineno {{ background-color: #f8d7da; color: #721c24; border-right-color: #f5c6cb; }}
        .partial .lineno {{ background-color: #fff3cd; color: #856404; border-right-color: #ffeeba; }}
        
        .annotation-toggle {{ color: #fff; background-color: #dc3545; padding: 2px 8px; border-radius: 12px; font-size: 0.75em; cursor: pointer; font-weight: bold; white-space: nowrap; margin-left: 15px; vertical-align: middle; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; transition: background-color 0.2s; display: inline-block; }}
        .annotation-toggle:hover {{ background-color: #c82333; }}
        .partial .annotation-toggle {{ background-color: #ffc107; color: #212529; }}
        .partial .annotation-toggle:hover {{ background-color: #e0a800; }}
        
        .annotation-details {{ display: none; margin-top: 8px; margin-bottom: 5px; padding: 10px; background-color: #f8d7da; color: #721c24; border-left: 4px solid #dc3545; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; white-space: normal; font-size: 0.9em; border-radius: 0 4px 4px 0; box-shadow: 0 1px 3px rgba(0,0,0,0.1); }}
        .partial .annotation-details {{ background-color: #fff3cd; color: #856404; border-left-color: #ffc107; }}
        
        .line.has-details .code-content {{ cursor: pointer; }}
        .line.open .annotation-details {{ display: block; }}
        
        .condition-table {{ width: 100%; border-collapse: collapse; font-size: 0.9em; margin-top: 8px; border: 1px solid #dee2e6; background: #fff; }}
        .condition-table th, .condition-table td {{ border: 1px solid #dee2e6; padding: 6px 10px; text-align: left; color: #212529; }}
        .condition-table th {{ background-color: #f8f9fa; font-weight: 600; color: #495057; }}
        .condition-table tr.hit td {{ background-color: #e6f4ea; }}
        .condition-table tr.miss td {{ background-color: #fce4e4; }}
        .annotation-list {{ margin: 0; padding: 0; list-style: none; }}
    </style>
    <script>
        function toggleDetails(el, event) {{
            if (event && event.target.closest('.annotation-details') || (event && event.target.tagName.toLowerCase() === 'a')) return;
            var line = el.closest('.line');
            if (line) line.classList.toggle('open');
        }}
    </script>
</head>
<body>
    <div class="header">
        <a href="index.html">← Back to Index</a>
        <strong>{filename}</strong>
    </div>
    <div class="code-container">
        {code_html}
    </div>
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
    line_div += f'<div class="lineno">{lineno}</div>'
    line_div += f'<div class="code-content">{content}'

    if toggle_text:
        line_div += f"<span class='annotation-toggle'>{toggle_text}</span>"

    if details_html:
        line_div += f'<div class="annotation-details">{details_html}</div>'

    line_div += '</div></div>'
    return line_div
