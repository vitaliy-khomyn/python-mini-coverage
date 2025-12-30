"""
HTML templates and rendering helpers for the HTML reporter.
"""
import html

HTML_HEADER = """
<!DOCTYPE html>
<html>
<head>
    <title>Coverage Report</title>
    <meta charset="utf-8">
    <style>
        body { font-family: sans-serif; padding: 20px; }
        table { border-collapse: collapse; width: 100%; }
        th, td { border: 1px solid #ddd; padding: 8px; text-align: left; }
        th { background-color: #f2f2f2; }
        .header { margin-bottom: 20px; }
        .line { display: flex; }
        .lineno { width: 50px; color: #999; border-right: 1px solid #ddd; padding-right: 10px; margin-right: 10px; text-align: right; user-select: none; }
        pre { margin: 0; }
        .hit { background-color: #dff0d8; }
        .miss { background-color: #f2dede; }
        .partial { background-color: #fcf8e3; }
        .annotate { color: #a94442; font-size: 0.8em; margin-left: 20px; font-style: italic; }
    </style>
</head>
<body>
"""

HTML_FOOTER = """
</body>
</html>
"""


def render_index(total_pct: float, rows: str) -> str:
    """Render the main index page."""
    return f"""
    {HTML_HEADER}
    <div class="header">
        <h1>Coverage Report</h1>
        <p>Total Coverage: <strong>{total_pct:.0f}%</strong></p>
    </div>
    <table>
        <thead>
            <tr>
                <th>File</th>
                <th>Statements</th>
                <th>Missed</th>
                <th>Coverage</th>
            </tr>
        </thead>
        <tbody>
            {rows}
        </tbody>
    </table>
    {HTML_FOOTER}
    """


def render_file(filename: str, code_html: str) -> str:
    """Render a file coverage detail page."""
    return f"""
    {HTML_HEADER}
    <h3>{html.escape(filename)}</h3>
    {code_html}
    {HTML_FOOTER}
    """


def render_index_row(link: str, label: str, possible: int, missed: int, pct: float) -> str:
    """Render a single row in the index table."""
    return f"""
    <tr>
        <td><a href="{link}">{html.escape(label)}</a></td>
        <td>{possible}</td>
        <td>{missed}</td>
        <td>{pct:.0f}%</td>
    </tr>
    """


def render_code_line(lineno: int, content: str, css_class: str, annotation: str) -> str:
    """Render a single line of source code with highlights."""
    return f"""
    <div class="line {css_class}">
        <span class="lineno">{lineno}</span>
        <pre>{content}</pre>
        {annotation}
    </div>
    """
