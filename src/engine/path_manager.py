import fnmatch
import os
from pathlib import Path

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

        p = Path(path)
        if p.exists():
            result = str(p.resolve())
        else:
            if p.parent.exists():
                result = str(p.parent.resolve() / p.name)
            else:
                result = str(p.absolute())

        result = os.path.normcase(result)
        self._cache[path] = result
        return result

    def map_path(self, path: str) -> str:
        """
        Remap a file path based on the [paths] configuration.
        """
        path = self.canonicalize(path)
        # handle case where config is a dict (during init) or CoverageConfig
        paths_config = self.config.get('paths', {}) if isinstance(self.config, dict) else self.config.paths

        p = Path(path)
        for canonical, aliases in paths_config.items():
            for alias in aliases:
                norm_alias = os.path.normcase(alias)
                alias_p = Path(norm_alias)

                if p.is_relative_to(alias_p):
                    rel = p.relative_to(alias_p)
                    return str(Path(canonical) / rel)
                elif path == norm_alias:
                    return canonical
        return path

    def should_trace(self, filename: str, excluded_files: Set[str]) -> bool:
        """
        Determine if a file should be tracked based on project root and exclusions.
        """
        abs_path = self.canonicalize(filename)
        p = Path(abs_path)
        root_p = Path(self.project_root)

        if not p.is_relative_to(root_p) and abs_path != self.project_root:
            return False

        # check exclusions (exact match or directory prefix)
        for excluded in excluded_files:
            exc_p = Path(excluded)
            if p == exc_p or p.is_relative_to(exc_p):
                return False

        try:
            rel_path = p.relative_to(root_p).as_posix()
        except ValueError:
            return False

        omit_patterns = self.config.get('omit', []) if isinstance(self.config, dict) else self.config.omit
        filename_only = p.name

        for pattern in omit_patterns:
            # if pattern contains a separator, match against the full relative path
            if '/' in pattern or (os.sep != '/' and os.sep in pattern):
                if fnmatch.fnmatch(rel_path, pattern):
                    return False
            # otherwise, match against the filename only (prevents 'test_*' matching 'test_project/')
            elif fnmatch.fnmatch(filename_only, pattern):
                return False

        return True
