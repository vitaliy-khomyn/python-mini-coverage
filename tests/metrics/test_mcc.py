from src.metrics.mcc import MCCCoverage
from .base import TestMetricsBase


class TestMCCCoverage(TestMetricsBase):
    def setUp(self):
        self.metric = MCCCoverage()

    def test_mcc_name(self):
        self.assertEqual(self.metric.get_name(), "MCC")

    def test_mcc_stats_empty(self):
        stats = self.metric.calculate_stats(set(), set())
        self.assertEqual(stats['pct'], 100.0)
        self.assertEqual(stats['ratio'], "0/0")
