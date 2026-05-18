import unittest
import os
from unittest.mock import patch
from src.engine.path_manager import PathManager
from src.engine.config import CoverageConfig
from tests.test_utils import BaseTestCase


class TestPathManager(BaseTestCase):
    def setUp(self):
        super().setUp()
        self.config = CoverageConfig()
        self.pm = PathManager(self.test_dir, self.config)

    def test_canonicalize_existing_file(self):
        file_path = self.create_file("test.py", "x = 1")
        canonical = self.pm.canonicalize(file_path)
        self.assertEqual(canonical, os.path.normcase(os.path.realpath(file_path)))

    def test_canonicalize_non_existing_file_existing_dir(self):
        file_path = os.path.join(self.test_dir, "non_existent.py")
        canonical = self.pm.canonicalize(file_path)
        expected = os.path.normcase(os.path.join(os.path.realpath(self.test_dir), "non_existent.py"))
        self.assertEqual(canonical, expected)

    def test_canonicalize_non_existing_dir(self):
        file_path = os.path.join(self.test_dir, "non_existent_dir", "file.py")
        canonical = self.pm.canonicalize(file_path)
        expected = os.path.normcase(os.path.abspath(file_path))
        self.assertEqual(canonical, expected)

    @unittest.skipIf(os.name == 'nt', "Symlinks require admin privileges on Windows")
    def test_canonicalize_symlink(self):
        target = self.create_file("target.py", "x = 1")
        symlink_path = os.path.join(self.test_dir, "link.py")
        os.symlink(target, symlink_path)

        canonical = self.pm.canonicalize(symlink_path)
        self.assertEqual(canonical, os.path.normcase(os.path.realpath(target)))

    def test_map_path_no_match(self):
        path = os.path.join(self.test_dir, "test.py")
        self.assertEqual(self.pm.map_path(path), os.path.normcase(os.path.realpath(path)))

    def test_map_path_logic(self):
        """Test _map_path with configured aliases."""
        src_alias = os.path.normcase(os.path.abspath("/w/source/"))
        src_canonical = os.path.normcase(os.path.abspath("/src/"))

        self.config.paths = {
            src_canonical: [src_alias]
        }

        with patch('pathlib.Path.exists', return_value=False):
            # Case 1: Match found
            input_path = os.path.join(src_alias, "file.py")
            mapped = self.pm.map_path(input_path)
            expected = os.path.join(src_canonical, "file.py")
            self.assertEqual(mapped, expected)

            # Case 2: No match
            nomatch_path = os.path.normcase(os.path.abspath("/nomatch/file.py"))
            mapped = self.pm.map_path(nomatch_path)
            self.assertEqual(mapped, nomatch_path)

    def test_should_trace_exclude_directory(self):
        self.config.omit = {"vendor/*"}
        vendor_file = self.create_file("vendor/lib.py", "x = 1")
        self.assertFalse(self.pm.should_trace(vendor_file, set()))

    def test_should_trace_exclude_filename(self):
        self.config.omit = {"test_*.py"}
        test_file = self.create_file("test_something.py", "x = 1")
        self.assertFalse(self.pm.should_trace(test_file, set()))

    def test_should_trace_include_normal(self):
        self.config.omit = set()
        normal_file = self.create_file("src/main.py", "x = 1")
        self.assertTrue(self.pm.should_trace(normal_file, set()))

    def test_should_trace_outside_project(self):
        outside_file = "/tmp/outside.py" if os.name != 'nt' else "C:\\tmp\\outside.py"
        self.assertFalse(self.pm.should_trace(outside_file, set()))
