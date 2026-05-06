from typing import List, Any

from .formatters import (
    BaseFormatter, StatementFormatter, BranchFormatter, ConditionFormatter,
    FunctionFormatter, LoopFormatter, ClassFormatter, CallSiteFormatter,
    ExceptionFormatter, ReturnFormatter, MMCDCFormatter
)


class MetricDisplayConfig:
    def __init__(self, key: str, name: str, console_header: str, html_display: str, xml_key: str, formatter: BaseFormatter, is_xml_standard: bool = False) -> None:
        self.key = key
        self.name = name
        self.console_header = console_header
        self.html_display = html_display
        self.xml_key = xml_key
        self.formatter = formatter
        self.is_xml_standard = is_xml_standard


METRICS_REGISTRY = [
    MetricDisplayConfig('stmt', 'Statement', 'Stmt', 'Statements', 'lines', StatementFormatter(), True),
    MetricDisplayConfig('branch', 'Branch', 'Branch', 'Branches', 'branches', BranchFormatter(), True),
    MetricDisplayConfig('cond', 'Condition', 'Cond', 'Conditions', 'conditions', ConditionFormatter(), False),
    MetricDisplayConfig('func', 'Function', 'Func', 'Functions', 'functions', FunctionFormatter(), False),
    MetricDisplayConfig('loop', 'Loop', 'Loop', 'Loops', 'loops', LoopFormatter(), False),
    MetricDisplayConfig('class', 'Class', 'Class', 'Classes', 'classes', ClassFormatter(), False),
    MetricDisplayConfig('call', 'Call-Site', 'Call', 'Call-Sites', 'calls', CallSiteFormatter(), False),
    MetricDisplayConfig('exc', 'Exception', 'Exc', 'Exceptions', 'exceptions', ExceptionFormatter(), False),
    MetricDisplayConfig('ret', 'Return', 'Return', 'Returns', 'returns', ReturnFormatter(), False),
    MetricDisplayConfig('mmcdc', 'MMC/DC', 'MMC/DC', 'MMC/DC', 'mmcdc', MMCDCFormatter(), False),
]


def get_active_metrics(config: Any) -> List[MetricDisplayConfig]:
    active_names = getattr(config, 'report_metrics', None)
    if active_names:
        return [m for m in METRICS_REGISTRY if m.name in active_names or m.key in active_names]
    return METRICS_REGISTRY
