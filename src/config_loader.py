import os
import logging
import configparser
from typing import Optional, Set
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
            path = os.path.join(project_root, cand)
            if not os.path.exists(path):
                continue

            try:
                if cand.endswith('.toml'):
                    if tomllib:
                        self._load_toml(path, config)
                        break
                    else:
                        self.logger.warning(
                            "Found pyproject.toml but Python < 3.11 and 'tomli' not installed. Skipping.")
                else:
                    # INI-style parsing
                    if self._load_ini(path, config):
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

        # check for existence of ANY relevant section
        run_section: Optional[str] = None
        if parser.has_section('run'):
            run_section = 'run'
        elif parser.has_section('coverage:run'):
            run_section = 'coverage:run'

        report_section: Optional[str] = None
        if parser.has_section('report'):
            report_section = 'report'
        elif parser.has_section('coverage:report'):
            report_section = 'coverage:report'

        paths_section: Optional[str] = None
        if parser.has_section('paths'):
            paths_section = 'paths'
        elif parser.has_section('coverage:paths'):
            paths_section = 'coverage:paths'

        # if neither section exists, this isn't a valid config file for us
        if not run_section and not report_section and not paths_section:
            return False

        # parse run section
        if run_section:
            for key in ['omit', 'include', 'source']:
                if parser.has_option(run_section, key):
                    val = parser.get(run_section, key)
                    getattr(config, key).update(self._parse_list(val))

            if parser.has_option(run_section, 'branch'):
                config.branch = parser.getboolean(run_section, 'branch')

            if parser.has_option(run_section, 'concurrency'):
                config.concurrency = parser.get(run_section, 'concurrency').strip()

            if parser.has_option(run_section, 'data_file'):
                config.data_file = parser.get(run_section, 'data_file').strip()

        # parse report section
        if report_section and parser.has_option(report_section, 'exclude_lines'):
            val = parser.get(report_section, 'exclude_lines')
            config.exclude_lines.update(self._parse_list(val))

        # parse paths section
        if paths_section:
            for option in parser.options(paths_section):
                val = parser.get(paths_section, option)
                # key is the canonical name, Value is list of paths
                config.paths[option] = list(self._parse_list(val))

        return True

    def _load_toml(self, path: str, config: CoverageConfig) -> None:
        """Parse TOML configuration file (pyproject.toml)."""
        with open(path, 'rb') as f:
            data = tomllib.load(f)  # type: ignore

        tool = data.get('tool', {}).get('coverage', {})
        run = tool.get('run', {})
        report = tool.get('report', {})
        paths = tool.get('paths', {})

        if not run and not report and not paths:
            return

        # run section
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

        # report section
        if 'exclude_lines' in report:
            config.exclude_lines.update(report['exclude_lines'])

        # paths section
        if paths:
            # TOML structure for paths is Key = [List]
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
