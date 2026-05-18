import os
import logging
import configparser
from pathlib import Path
from typing import Optional, Set, Dict, Any
from .config import CoverageConfig

# try importing tomllib for pyproject.toml support (Python 3.11+)
try:
    import tomllib
except ImportError:
    tomllib = None


class ConfigLoader:
    """
    Loads configuration settings from standard config files.
    """

    def __init__(self) -> None:
        self.logger = logging.getLogger(__name__)

    def load_config(self, project_root: str, config_file: Optional[str] = None) -> CoverageConfig:
        """
        Load configuration from pyproject.toml, .coveragerc, setup.cfg, or a specified file.
        Supports environment variable overrides.

        Args:
            project_root (str): The root directory to search for config files.
            config_file (str): Optional explicit path to a config file.

        Returns:
            CoverageConfig: Configuration object with normalized options.
        """
        config = CoverageConfig()

        # check environment variables for overrides (highest precedence for file location)
        env_data_file = os.environ.get('COVERAGE_FILE')
        if env_data_file:
            config.data_file = env_data_file

        candidates = [config_file] if config_file else ['pyproject.toml', '.coveragerc', 'setup.cfg', 'tox.ini']

        for cand in candidates:
            if not cand:
                continue
            path = Path(project_root) / cand
            if not path.exists():
                continue

            try:
                if cand.endswith('.toml'):
                    if tomllib:
                        self._load_toml(str(path), config)
                        break
                    else:
                        self.logger.warning(
                            "Found pyproject.toml but Python < 3.11 and 'tomli' not installed. Skipping.")
                else:
                    # INI-style parsing
                    if self._load_ini(str(path), config):
                        break
            except Exception as e:
                self.logger.warning(f"Failed to parse configuration file {path}: {e}")

        return config

    def _load_ini(self, path: str, config: CoverageConfig) -> bool:
        """Parse INI configuration file."""
        parser = configparser.ConfigParser()
        try:
            parser.read(path)
        except configparser.Error as e:
            raise ValueError(f"INI parse error: {e}")

        def _get_section(base_name: str) -> Optional[str]:
            if parser.has_section(base_name):
                return base_name
            if parser.has_section(f"coverage:{base_name}"):
                return f"coverage:{base_name}"
            return None

        # check for existence of ANY relevant section
        run_section = _get_section('run')
        report_section = _get_section('report')
        paths_section = _get_section('paths')

        # if neither section exists, this isn't a valid config file for us
        if not run_section and not report_section and not paths_section:
            return False

        run_data = {}
        if run_section:
            for key in ['omit', 'include', 'source']:
                if parser.has_option(run_section, key):
                    run_data[key] = self._parse_list(parser.get(run_section, key))

            if parser.has_option(run_section, 'branch'):
                run_data['branch'] = parser.getboolean(run_section, 'branch')

            for key in ['concurrency', 'data_file']:
                if parser.has_option(run_section, key):
                    run_data[key] = parser.get(run_section, key).strip()

        report_data = {}
        if report_section:
            if parser.has_option(report_section, 'exclude_lines'):
                report_data['exclude_lines'] = self._parse_list(parser.get(report_section, 'exclude_lines'))
            if parser.has_option(report_section, 'metrics'):
                report_data['metrics'] = list(self._parse_list(parser.get(report_section, 'metrics')))

        paths_data = {}
        if paths_section:
            for option in parser.options(paths_section):
                paths_data[option] = list(self._parse_list(parser.get(paths_section, option)))

        self._populate_config(run_data, report_data, paths_data, config)
        return True

    def _load_toml(self, path: str, config: CoverageConfig) -> None:
        """Parse TOML configuration file (pyproject.toml)."""
        with open(path, 'rb') as f:
            data = tomllib.load(f)  # type: ignore

        tool = data.get('tool', {}).get('coverage', {})
        self._populate_config(tool.get('run', {}), tool.get('report', {}), tool.get('paths', {}), config)

    def _populate_config(self, run: Dict[str, Any], report: Dict[str, Any], paths: Dict[str, Any], config: CoverageConfig) -> None:
        """Helper to populate CoverageConfig from raw dictionary data."""
        if 'omit' in run:
            config.omit.update(run['omit'])
        if 'include' in run:
            config.include.update(run['include'])
        if 'source' in run:
            config.source.update(run['source'])
        if 'branch' in run:
            config.branch = bool(run['branch'])
        if 'concurrency' in run:
            config.concurrency = str(run['concurrency'])
        if 'data_file' in run:
            config.data_file = str(run['data_file'])

        if 'exclude_lines' in report:
            config.exclude_lines.update(report['exclude_lines'])
        if 'metrics' in report:
            config.report_metrics = list(report['metrics'])

        if paths:
            config.paths = paths

    def _parse_list(self, raw_str: str) -> Set[str]:
        """Helper to parse multiline or comma-separated strings into a set."""
        result = set()
        # handle both newline and comma separators
        for line in raw_str.replace(',', '\n').splitlines():
            clean = line.strip()
            if clean:
                result.add(clean)
        return result
