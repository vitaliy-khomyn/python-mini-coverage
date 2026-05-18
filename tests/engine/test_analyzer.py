import unittest  # noqa: F401
import ast
from unittest.mock import MagicMock, patch
from src.engine import MiniCoverage
from tests.test_utils import BaseTestCase
from src.engine.trace_data import TraceDataType


class TestAnalyzer(BaseTestCase):
    def setUp(self):
        super().setUp()
        self.cov = MiniCoverage(project_root=self.test_dir)

    def test_analyze_aggregation(self):
        """Test that analyze aggregates data from multiple raw paths mapping to same file."""
        with patch('os.path.normcase', side_effect=lambda p: p.lower()):
            with patch('os.path.realpath', side_effect=lambda p, **kwargs: p):
                with patch('pathlib.Path.exists', return_value=True):
                    f1 = "File.py"
                    f2 = "file.py"

                    self.cov.trace_data[TraceDataType.LINES][f1][0].add(1)
                    self.cov.trace_data[TraceDataType.LINES][f2][0].add(2)

                    real_ast = ast.parse("x=1\ny=2")
                    real_code = compile("x=1\ny=2", "file.py", "exec")

                    self.cov.parser.parse_source = MagicMock(return_value=(real_ast, set()))
                    self.cov.parser.compile_source = MagicMock(return_value=real_code)
                    self.cov.path_manager.should_trace = MagicMock(return_value=True)

                    results = self.cov.analyze()

                    self.assertEqual(len(results), 1)
                    result_key = list(results.keys())[0]
                    stmt_stats = results[result_key]["Statement"]
                    self.assertEqual(len(stmt_stats['executed']), 2)
