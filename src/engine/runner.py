import logging
import sys
import types
from pathlib import Path
from typing import Optional, List, Any


class ScriptRunner:
    def __init__(self, engine: Any):
        self.engine = engine
        self.logger = logging.getLogger(__name__)

    def run(self, script_path: str, script_args: Optional[List[str]] = None) -> None:
        abs_script_path = self.engine.path_manager.canonicalize(script_path)
        script_dir = str(Path(abs_script_path).parent)

        original_argv = sys.argv
        original_path = sys.path[:]

        sys.argv = [script_path] + (script_args if script_args else [])
        sys.path.insert(0, script_dir)

        if self.engine.project_root not in sys.path:
            sys.path.insert(0, self.engine.project_root)

        main_mod = types.ModuleType("__main__")
        main_mod.__file__ = abs_script_path
        main_mod.__builtins__ = __builtins__

        old_main = sys.modules.get('__main__')
        sys.modules['__main__'] = main_mod

        try:
            with open(abs_script_path, 'rb') as f:
                code = compile(f.read(), abs_script_path, 'exec')

            self.engine.start()
            exec(code, main_mod.__dict__)

        except SystemExit as e:
            self.logger.debug(f"SystemExit caught during execution: {e}")
            raise
        except Exception as e:
            self.logger.error(f"Exception during execution: {e}")
            raise
        finally:
            self.engine.stop()
            sys.argv = original_argv
            sys.path = original_path
            if old_main is not None:
                sys.modules['__main__'] = old_main
            else:
                del sys.modules['__main__']
