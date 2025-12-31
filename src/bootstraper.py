"""
This module is intended to be imported during Python startup
(e.g., via a .pth file in site-packages or sitecustomize.py).
It checks for environment variables and auto-starts coverage.
"""
import os
import sys
import logging


def bootstrap():
    """
    Check environment variables and start MiniCoverage if configured.
    """
    config_file = os.environ.get("MINICOV_CONFIG")
    # only bootstrap if explicitly requested via env var
    if not config_file:
        return

    logger = logging.getLogger("minicov.bootstrap")

    # avoid infinite recursion or double tracing if already active
    if sys.gettrace():
        return

    try:
        # we need to ensure src is in path if we are running from source
        # in a real install, this would be handled by pip
        project_root = os.environ.get("MINICOV_ROOT")
        if project_root and project_root not in sys.path:
            sys.path.insert(0, project_root)

        # import locally to avoid polluting global namespace too early
        from src.engine import MiniCoverage

        # initialize and start
        # use CWD as root or infer from config?
        # usually project root is implicitly CWD for coverage runs
        cov = MiniCoverage(config_file=config_file)
        cov.start()

        # register an exit handler to save data cleanly
        import atexit
        atexit.register(cov.stop)

    except ImportError as e:
        # MiniCoverage not found, skip
        logger.debug(f"MiniCoverage not found during bootstrap: {e}")
    except Exception as e:
        # print warning but don't crash the user's process
        logger.warning(f"Bootstrapping failed: {e}")


# auto-execute on import
bootstrap()
