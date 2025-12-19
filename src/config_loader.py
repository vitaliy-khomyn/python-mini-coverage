import os
import configparser


class ConfigLoader:
    """
    Responsible for loading configuration from files (.coveragerc, setup.cfg).
    """

    def load_config(self, project_root, config_file=None):
        config = {
            'omit': set()
        }

        # Default search paths if no specific file provided
        candidates = [config_file] if config_file else ['.coveragerc', 'setup.cfg', 'tox.ini']

        parser = configparser.ConfigParser()

        for cand in candidates:
            if not cand: continue
            path = os.path.join(project_root, cand)
            if os.path.exists(path):
                try:
                    parser.read(path)
                    # Check for [run] or [coverage:run] sections
                    section = None
                    if parser.has_section('run'):
                        section = 'run'
                    elif parser.has_section('coverage:run'):
                        section = 'coverage:run'

                    if section and parser.has_option(section, 'omit'):
                        omit_str = parser.get(section, 'omit')
                        # Handle multiline or comma-separated lists
                        for line in omit_str.replace(',', '\n').splitlines():
                            clean = line.strip()
                            if clean:
                                config['omit'].add(clean)

                    # Stop after finding the first valid config file
                    break
                except configparser.Error:
                    pass

        return config