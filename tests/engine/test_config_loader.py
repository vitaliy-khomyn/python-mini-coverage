import os
import unittest  # noqa: F401
from unittest.mock import patch
from src.engine.config_loader import ConfigLoader
from tests.test_utils import BaseTestCase


class TestConfigLoader(BaseTestCase):
    def setUp(self):
        super().setUp()
        self.loader = ConfigLoader()

    def test_env_var_override(self):
        with patch.dict(os.environ, {"COVERAGE_FILE": ".custom.db"}):
            config = self.loader.load_config(self.test_dir)
            self.assertEqual(config.data_file, ".custom.db")

    def test_toml_parsing(self):
        toml_content = """
[tool.coverage.run]
branch = true
omit = ["test_*.py"]
concurrency = "multiprocessing"
data_file = ".my_cov.db"

[tool.coverage.report]
exclude_lines = ["pragma: no cover"]

[tool.coverage.paths]
source = ["src/"]
"""
        self.create_file("pyproject.toml", toml_content)

        try:
            import tomllib  # noqa: F401
        except ImportError:
            self.skipTest("tomllib not available")

        config = self.loader.load_config(self.test_dir)
        self.assertTrue(config.branch)
        self.assertIn("test_*.py", config.omit)
        self.assertEqual(config.concurrency, "multiprocessing")
        self.assertEqual(config.data_file, ".my_cov.db")
        self.assertIn("pragma: no cover", config.exclude_lines)
        self.assertEqual(config.paths, {"source": ["src/"]})

    def test_toml_parsing_no_tomllib(self):
        toml_content = """
[tool.coverage.run]
branch = true
"""
        self.create_file("pyproject.toml", toml_content)

        # Mock tomllib to None
        with patch('src.engine.config_loader.tomllib', None):
            with self.assertLogs('src.engine.config_loader', level='WARNING') as cm:
                config = self.loader.load_config(self.test_dir)
                self.assertFalse(config.branch) # Should not have been parsed
                self.assertTrue(any("tomli' not installed" in o for o in cm.output))

    def test_load_ini_invalid(self):
        ini_content = "[unclosed_section"
        self.create_file("setup.cfg", ini_content)

        with self.assertLogs('src.engine.config_loader', level='WARNING') as cm:
            self.loader.load_config(self.test_dir)
            self.assertTrue(any("Failed to parse configuration file" in o for o in cm.output))
