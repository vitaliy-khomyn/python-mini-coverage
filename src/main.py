import sys
from .engine import MiniCoverage

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python -m src.main <script_to_run.py> [args...]")
        sys.exit(1)

    target = sys.argv[1]
    args = sys.argv[2:]

    cov = MiniCoverage()
    cov.run(target, args)
    cov.report()