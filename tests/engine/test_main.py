import unittest
import sys
import os
from unittest.mock import patch
from src.main import main


class TestMainCLI(unittest.TestCase):
    @patch('src.main.MiniCoverage')
    @patch('pathlib.Path.is_file')
    def test_run_command_basic(self, mock_isfile, mock_minicoverage):
        mock_isfile.return_value = True
        test_args = ["minicov", "run", "script.py", "arg1"]
        with patch.object(sys, 'argv', test_args):
            main()

        mock_minicoverage.assert_called_once()
        kwargs = mock_minicoverage.call_args[1]
        self.assertTrue(kwargs.get('erase_on_start', False))

        mock_cov_instance = mock_minicoverage.return_value
        mock_cov_instance.run.assert_called_once_with("script.py", ["arg1"])

    @patch('src.main.MiniCoverage')
    @patch('pathlib.Path.is_file')
    def test_run_command_preserve(self, mock_isfile, mock_minicoverage):
        mock_isfile.return_value = True
        test_args = ["minicov", "run", "--preserve", "script.py"]
        with patch.object(sys, 'argv', test_args):
            main()

        mock_minicoverage.assert_called_once()
        kwargs = mock_minicoverage.call_args[1]
        self.assertFalse(kwargs.get('erase_on_start', True))

    @patch('pathlib.Path.is_file')
    def test_run_missing_script(self, mock_isfile):
        mock_isfile.return_value = False
        test_args = ["minicov", "run", "missing.py"]
        with patch.object(sys, 'argv', test_args):
            with self.assertRaises(SystemExit) as cm:
                main()
        self.assertEqual(cm.exception.code, 1)

    @patch('src.main.MiniCoverage')
    def test_report_command(self, mock_minicoverage):
        test_args = ["minicov", "report", "--format", "json", "xml"]
        with patch.object(sys, 'argv', test_args):
            main()

        mock_cov_instance = mock_minicoverage.return_value
        mock_cov_instance.report.assert_called_once_with(reporters=["json", "xml"])

    @patch('src.main.MiniCoverage')
    def test_combine_command(self, mock_minicoverage):
        test_args = ["minicov", "combine"]
        with patch.object(sys, 'argv', test_args):
            main()

        mock_cov_instance = mock_minicoverage.return_value
        mock_cov_instance.combine_data.assert_called_once()

    @patch('src.main.MiniCoverage')
    @patch('pathlib.Path.is_file')
    @patch('pathlib.Path.exists', autospec=True)
    def test_run_auto_config(self, mock_exists, mock_isfile, mock_minicoverage):
        mock_isfile.return_value = True

        def exists_side_effect(path_self):
            return str(path_self).endswith('.coveragerc')
        mock_exists.side_effect = exists_side_effect

        test_args = ["minicov", "run", "some_dir/script.py"]
        with patch.object(sys, 'argv', test_args):
            main()

        kwargs = mock_minicoverage.call_args[1]
        expected_config = os.path.join(os.path.dirname(os.path.abspath("some_dir/script.py")), ".coveragerc")
        self.assertEqual(kwargs.get('config_file'), expected_config)
