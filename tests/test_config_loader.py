import unittest
import os
from src.config_loader import ConfigLoader
from tests.test_utils import BaseTestCase


class TestConfigLoader(BaseTestCase):

    def setUp(self):
        super().setUp()
        self.loader = ConfigLoader()

    def test_defaults_no_file(self):
        config = self.loader.load_config(self.test_dir)
        self.assertEqual(config['omit'], set())
        self.assertEqual(config['data_file'], ".coverage.db")

    def test_load_coveragerc_simple(self):
        content = """
[run]
omit = tests/*
       setup.py
"""
        self.create_file(".coveragerc", content)
        config = self.loader.load_config(self.test_dir)
        self.assertIn("tests/*", config['omit'])
        self.assertIn("setup.py", config['omit'])

    def test_load_coveragerc_comma_separated(self):
        content = """
[run]
omit = file1.py, file2.py, dir/
"""
        self.create_file(".coveragerc", content)
        config = self.loader.load_config(self.test_dir)
        self.assertIn("file1.py", config['omit'])
        self.assertIn("file2.py", config['omit'])
        self.assertIn("dir/", config['omit'])

    def test_load_setup_cfg(self):
        content = """
[coverage:run]
omit = 
    generated.py
"""
        self.create_file("setup.cfg", content)
        config = self.loader.load_config(self.test_dir)
        self.assertIn("generated.py", config['omit'])

    def test_data_file_option(self):
        content = """
[run]
data_file = my_coverage.sqlite
"""
        self.create_file(".coveragerc", content)
        config = self.loader.load_config(self.test_dir)
        self.assertEqual(config['data_file'], "my_coverage.sqlite")

    def test_precedence_explicit_file(self):
        # Create both default files
        self.create_file(".coveragerc", "[run]\nomit=A")
        self.create_file("setup.cfg", "[coverage:run]\nomit=B")

        # Create explicit file
        custom_path = self.create_file("my.ini", "[run]\nomit=C")

        config = self.loader.load_config(self.test_dir, config_file="my.ini")
        self.assertEqual(config['omit'], {'C'})

    def test_precedence_coveragerc_over_setupcfg(self):
        self.create_file(".coveragerc", "[run]\nomit=A")
        self.create_file("setup.cfg", "[coverage:run]\nomit=B")

        config = self.loader.load_config(self.test_dir)
        # Loader looks for candidates in order: .coveragerc, setup.cfg
        # Should pick .coveragerc and stop
        self.assertEqual(config['omit'], {'A'})

    def test_malformed_config(self):
        self.create_file(".coveragerc", "NOT A INI FILE")
        config = self.loader.load_config(self.test_dir)
        # Should fail gracefully and return defaults
        self.assertEqual(config['omit'], set())
        self.assertEqual(config['data_file'], ".coverage.db")

    def test_empty_omit(self):
        self.create_file(".coveragerc", "[run]\nomit=")
        config = self.loader.load_config(self.test_dir)
        self.assertEqual(config['omit'], set())

    def test_section_missing(self):
        self.create_file(".coveragerc", "[html]\ndirectory=htmlcov")
        config = self.loader.load_config(self.test_dir)
        self.assertEqual(config['omit'], set())

    def test_option_missing(self):
        self.create_file(".coveragerc", "[run]\nparallel=True")
        config = self.loader.load_config(self.test_dir)
        self.assertEqual(config['omit'], set())