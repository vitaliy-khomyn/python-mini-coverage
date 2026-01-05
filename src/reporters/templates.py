"""
HTML templates and rendering helpers for the HTML reporter.
"""


def render_index(stmt_pct, branch_pct, cond_pct, rows):
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
</head>
<body>
    <h1>Coverage Report</h1>
    <div class="summary">
        <strong>Total Coverage:</strong> 
        Statements: <span class="{_get_css_class(stmt_pct)}">{stmt_pct:.1f}%</span> | 
        Branches: <span class="{_get_css_class(branch_pct)}">{branch_pct:.1f}%</span> | 
        Conditions (MC/DC): <span class="{_get_css_class(cond_pct)}">{cond_pct:.1f}%</span>
    </div>
    <table>
        <thead>
            <tr>
                <th>File</th>
                <th class="numeric">Statements</th>
                <th class="numeric">Branches</th>
                <th class="numeric">Conditions</th>
            </tr>
        </thead>
        <tbody>
            {rows}
        </tbody>
    </table>
</body>
</html>
"""


def render_index_row(link, filename, stmt_data, branch_data, cond_data):
    return f"""
    <tr>
        <td><a href="{link}">{filename}</a></td>
        {_render_cell(stmt_data)}
        {_render_cell(branch_data)}
        {_render_cell(cond_data)}
    </tr>
    """


def _render_cell(metric_data):
    if not metric_data or not metric_data.get('possible'):
        return '<td class="numeric na">N/A</td>'


    pct = metric_data.get('pct', 0)
    css = _get_css_class(pct)
    return f'<td class="numeric {css}">{pct:.0f}%</td>'


def _get_css_class(pct):
    if pct >= 90: return "good"
    if pct >= 70: return "warn"
    return "bad"


def render_file(filename, code_html):
    return f"""
<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <title>Coverage: {filename}</title>
    <style>
        body {{ font-family: monospace; white-space: pre; margin: 0; padding: 0; }}
        .line {{ display: block; padding: 0 5px; }}
        .lineno {{ color: #999; padding-right: 10px; user-select: none; }}
        .hit {{ background-color: #d4edda; }}
        .miss {{ background-color: #f8d7da; }}
        .partial {{ background-color: #fff3cd; }}
        .annotate {{ color: #856404; font-weight: bold; float: right; margin-left: 20px; }}
    </style>
</head>
<body>
    {code_html}
</body>
</html>
"""


def render_code_line(lineno, content, css_class, annotation):
    # content is already escaped
    line_div = f'<div class="line {css_class}">'
    line_div += f'<span class="lineno">{lineno}</span>'

    if annotation:
        line_div += annotation

    line_div += content
    line_div += '</div>'
    return line_div
