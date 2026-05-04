from typing import List, Any


class MetricDisplayConfig:
    def __init__(self, key: str, name: str, console_header: str, html_display: str, xml_key: str, is_xml_standard: bool = False) -> None:
        self.key = key
        self.name = name
        self.console_header = console_header
        self.html_display = html_display
        self.xml_key = xml_key
        self.is_xml_standard = is_xml_standard


METRICS_REGISTRY = [
    MetricDisplayConfig('stmt', 'Statement', 'Stmt', 'Statements', 'lines', True),
    MetricDisplayConfig('branch', 'Branch', 'Branch', 'Branches', 'branches', True),
    MetricDisplayConfig('cond', 'Condition', 'Cond', 'Conditions', 'conditions', False),
    MetricDisplayConfig('func', 'Function', 'Func', 'Functions', 'functions', False),
    MetricDisplayConfig('loop', 'Loop', 'Loop', 'Loops', 'loops', False),
    MetricDisplayConfig('class', 'Class', 'Class', 'Classes', 'classes', False),
    MetricDisplayConfig('call', 'Call-Site', 'Call', 'Call-Sites', 'calls', False),
    MetricDisplayConfig('exc', 'Exception', 'Exc', 'Exceptions', 'exceptions', False),
    MetricDisplayConfig('ret', 'Return', 'Return', 'Returns', 'returns', False),
]


def get_active_metrics(config: Any) -> List[MetricDisplayConfig]:
    active_names = getattr(config, 'report_metrics', None)
    if active_names:
        return [m for m in METRICS_REGISTRY if m.name in active_names or m.key in active_names]
    return METRICS_REGISTRY
