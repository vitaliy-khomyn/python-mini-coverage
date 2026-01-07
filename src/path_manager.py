import os
import fnmatch
from typing import Dict, Any, Set


class PathManager:
    """
    Centralizes path normalization, canonicalization, and filtering logic.
    """
    def __init__(self, project_root: str, config: Dict[str, Any]):
        self.project_root = self.canonicalize(project_root)
        self.config = config

    @staticmethod
    def canonicalize(path: str) -> str:
        """
        Convert a path to its canonical form: absolute, symlinks resolved, case-normalized.
        """
        # Use realpath to resolve symlinks (crucial for deduplication)
        # Fallback to abspath if file doesn't exist
        if os.path.exists(path):
            return os.path.normcase(os.path.realpath(path))

        # If file doesn't exist, try to resolve the directory part
        # This ensures that if project_root is realpath'ed, files inside it are too.
        head, tail = os.path.split(os.path.abspath(path))
        if os.path.exists(head):
            return os.path.normcase(os.path.join(os.path.realpath(head), tail))

        return os.path.normcase(os.path.abspath(path))

    def map_path(self, path: str) -> str:
        """
        Remap a file path based on the [paths] configuration.
        """
        path = self.canonicalize(path)
        for canonical, aliases in self.config.get('paths', {}).items():
            for alias in aliases:
                norm_alias = os.path.normcase(alias)
                if path.startswith(norm_alias):
                    return path.replace(norm_alias, canonical, 1)
        return path

    def should_trace(self, filename: str, excluded_files: Set[str]) -> bool:
        """
        Determine if a file should be tracked based on project root and exclusions.
        """
        abs_path = self.canonicalize(filename)

        if not abs_path.startswith(self.project_root):
            return False
        if abs_path in excluded_files:
            return False

        rel_path = os.path.relpath(abs_path, self.project_root)
        # normalize to forward slashes for consistent pattern matching
        rel_path = rel_path.replace(os.sep, '/')

        for pattern in self.config.get('omit', []):
            if fnmatch.fnmatch(rel_path, pattern):
                return False

        return True
