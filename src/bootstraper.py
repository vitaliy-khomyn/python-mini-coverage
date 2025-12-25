"""
This module is intended to be imported during Python startup
(e.g., via a .pth file in site-packages or sitecustomize.py).
It checks for environment variables and auto-starts coverage.
"""
import os
import sys


def bootstrap():
    """
    Check environment variables and start MiniCoverage if configured.
    """
    config_file = os.environ.get("MINICOV_CONFIG")
    # Only bootstrap if explicitly requested via env var
    if not config_file:
        return

    # Avoid infinite recursion or double tracing if already active
    if sys.gettrace():
        return

    try:
        # We need to ensure src is in path if we are running from source
        # In a real install, this would be handled by pip
        project_root = os.environ.get("MINICOV_ROOT")
        if project_root and project_root not in sys.path:
            sys.path.insert(0, project_root)

        # Import locally to avoid polluting global namespace too early
        from src.engine import MiniCoverage

        # Initialize and start
        # Use CWD as root or infer from config?
        # Usually project root is implicitly CWD for coverage runs
        cov = MiniCoverage(config_file=config_file)
        cov.start()

        # Register an exit handler to save data cleanly
        import atexit
        atexit.register(cov.stop)

    except ImportError:
        # MiniCoverage not found, skip
        pass
    except Exception as e:
        # Print warning but don't crash the user's process
        print(f"[MiniCoverage] Bootstrapping failed: {e}", file=sys.stderr)


# Auto-execute on import
bootstrap()