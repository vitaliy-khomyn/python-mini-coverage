import os
import configparser
from typing import Optional, Dict, Any, Set


class ConfigLoader:
    """
    Loads configuration settings from standard config files.
    """

    def load_config(self, project_root: str, config_file: Optional[str] = None) -> Dict[str, Any]:
        """
        Load configuration from .coveragerc, setup.cfg, or a specified file.

        Args:
            project_root (str): The root directory to search for config files.
            config_file (str): Optional explicit path to a config file.

        Returns:
            dict: Configuration dictionary with keys like 'omit' (set) and 'data_file' (str).
        """
        config: Dict[str, Any] = {
            'omit': set(),
            'data_file': '.coverage.db'
        }

        candidates = [config_file] if config_file else ['.coveragerc', 'setup.cfg', 'tox.ini']

        parser = configparser.ConfigParser()

        for cand in candidates:
            if not cand: continue
            path = os.path.join(project_root, cand)
            if os.path.exists(path):
                try:
                    parser.read(path)

                    section: Optional[str] = None
                    if parser.has_section('run'):
                        section = 'run'
                    elif parser.has_section('coverage:run'):
                        section = 'coverage:run'

                    if section:
                        if parser.has_option(section, 'omit'):
                            omit_str = parser.get(section, 'omit')
                            for line in omit_str.replace(',', '\n').splitlines():
                                clean = line.strip()
                                if clean:
                                    config['omit'].add(clean)

                        if parser.has_option(section, 'data_file'):
                            config['data_file'] = parser.get(section, 'data_file').strip()

                    break
                except configparser.Error:
                    pass

        return config