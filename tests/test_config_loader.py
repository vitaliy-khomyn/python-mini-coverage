import os
import sys  # noqa: F401
import logging
import configparser
from typing import Optional, Dict, Any, Set

# Try importing tomllib for pyproject.toml support (Python 3.11+)
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

    def load_config(self, project_root: str, config_file: Optional[str] = None) -> Dict[str, Any]:
        """
        Load configuration from pyproject.toml, .coveragerc, setup.cfg, or a specified file.
        Supports environment variable overrides.

        Args:
            project_root (str): The root directory to search for config files.
            config_file (str): Optional explicit path to a config file.

        Returns:
            dict: Configuration dictionary with normalized options.
        """
        config: Dict[str, Any] = {
            'omit': set(),
            'include': set(),
            'source': set(),
            'branch': False,
            'concurrency': 'thread',
            'exclude_lines': set(),
            'data_file': '.coverage.db'
        }

        # Check environment variables for overrides (highest precedence for file location)
        env_data_file = os.environ.get('COVERAGE_FILE')
        if env_data_file:
            config['data_file'] = env_data_file

        candidates = [config_file] if config_file else ['pyproject.toml', '.coveragerc', 'setup.cfg', 'tox.ini']

        for cand in candidates:
            if not cand: continue
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

    def _load_ini(self, path: str, config: Dict[str, Any]) -> bool:
        """Parse INI configuration file."""
        parser = configparser.ConfigParser()
        try:
            parser.read(path)
        except configparser.Error as e:
            raise ValueError(f"INI parse error: {e}")

        section: Optional[str] = None
        if parser.has_section('run'):
            section = 'run'
        elif parser.has_section('coverage:run'):
            section = 'coverage:run'

        if not section:
            return False

        # Parse List Options
        for key in ['omit', 'include', 'source']:
            if parser.has_option(section, key):
                val = parser.get(section, key)
                config[key].update(self._parse_list(val))

        # Parse Boolean Options
        if parser.has_option(section, 'branch'):
            config['branch'] = parser.getboolean(section, 'branch')

        # Parse String Options
        if parser.has_option(section, 'concurrency'):
            config['concurrency'] = parser.get(section, 'concurrency').strip()

        if parser.has_option(section, 'data_file'):
            config['data_file'] = parser.get(section, 'data_file').strip()

        # Parse Report Section for exclude_lines
        report_section = None
        if parser.has_section('report'):
            report_section = 'report'
        elif parser.has_section('coverage:report'):
            report_section = 'coverage:report'

        if report_section and parser.has_option(report_section, 'exclude_lines'):
            val = parser.get(report_section, 'exclude_lines')
            config['exclude_lines'].update(self._parse_list(val))

        return True

    def _load_toml(self, path: str, config: Dict[str, Any]) -> None:
        """Parse TOML configuration file (pyproject.toml)."""
        with open(path, 'rb') as f:
            data = tomllib.load(f)  # type: ignore

        tool = data.get('tool', {}).get('coverage', {})
        run = tool.get('run', {})
        report = tool.get('report', {})

        if not run and not report:
            return

        # Run section
        if 'omit' in run:
            config['omit'].update(run['omit'])
        if 'include' in run:
            config['include'].update(run['include'])
        if 'source' in run:
            config['source'].update(run['source'])
        if 'branch' in run:
            config['branch'] = bool(run['branch'])
        if 'concurrency' in run:
            config['concurrency'] = str(run['concurrency'])
        if 'data_file' in run:
            config['data_file'] = str(run['data_file'])

        # Report section
        if 'exclude_lines' in report:
            config['exclude_lines'].update(report['exclude_lines'])

    def _parse_list(self, raw_str: str) -> Set[str]:
        """Helper to parse multiline or comma-separated strings into a set."""
        result = set()
        # Handle both newline and comma separators
        for line in raw_str.replace(',', '\n').splitlines():
            clean = line.strip()
            if clean:
                result.add(clean)
        return result
