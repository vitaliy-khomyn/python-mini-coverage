import fnmatch
import os

from typing import Set
from .config import CoverageConfig


class PathManager:
    """
    Centralizes path normalization, canonicalization, and filtering logic.
    """
    def __init__(self, project_root: str, config: CoverageConfig):
        self._cache = {}
        self.project_root = self.canonicalize(project_root)
        self.config = config

    def canonicalize(self, path: str) -> str:
        """
        Convert a path to its canonical form: absolute, symlinks resolved, case-normalized.
        """
        if path in self._cache:
            return self._cache[path]

        # Fallback to abspath if file doesn't exist
        if os.path.exists(path):
            result = os.path.normcase(os.path.realpath(path))
            self._cache[path] = result
            return result

        # If file doesn't exist, try to resolve the directory part
        # This ensures that if project_root is realpath'ed, files inside it are too.
        head, tail = os.path.split(os.path.abspath(path))
        if os.path.exists(head):
            result = os.path.normcase(os.path.join(os.path.realpath(head), tail))
            self._cache[path] = result
            return result

        result = os.path.normcase(os.path.abspath(path))
        self._cache[path] = result
        return result

    def map_path(self, path: str) -> str:
        """
        Remap a file path based on the [paths] configuration.
        """
        path = self.canonicalize(path)
        # handle case where config is a dict (during init) or CoverageConfig
        paths_config = self.config.get('paths', {}) if isinstance(self.config, dict) else self.config.paths

        for canonical, aliases in paths_config.items():
            for alias in aliases:
                norm_alias = os.path.normcase(alias)
                # verify directory boundary to prevent prefix collisions
                if path == norm_alias or path.startswith(norm_alias + ('' if norm_alias.endswith(os.sep) else os.sep)):
                    return path.replace(norm_alias, canonical, 1)
        return path

    def should_trace(self, filename: str, excluded_files: Set[str]) -> bool:
        """
        Determine if a file should be tracked based on project root and exclusions.
        """
        abs_path = self.canonicalize(filename)

        if not abs_path.startswith(self.project_root):
            return False

        # check exclusions (exact match or directory prefix)
        for excluded in excluded_files:
            if abs_path == excluded or abs_path.startswith(excluded + os.sep):
                return False

        try:
            rel_path = os.path.relpath(abs_path, self.project_root)
        except ValueError:
            return False

        # normalize to forward slashes for consistent pattern matching
        rel_path = rel_path.replace(os.sep, '/')

        omit_patterns = self.config.get('omit', []) if isinstance(self.config, dict) else self.config.omit
        filename_only = os.path.basename(abs_path)

        for pattern in omit_patterns:
            # if pattern contains a separator, match against the full relative path
            if '/' in pattern or (os.sep != '/' and os.sep in pattern):
                if fnmatch.fnmatch(rel_path, pattern):
                    return False
            # otherwise, match against the filename only (prevents 'test_*' matching 'test_project/')
            elif fnmatch.fnmatch(filename_only, pattern):
                return False

        return True
