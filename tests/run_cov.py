import sys
import os
import unittest

# 1. setup paths
current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(current_dir)

# add project root to sys.path to allow importing 'src'
if project_root not in sys.path:
    sys.path.insert(0, project_root)

# add hand_tests to sys.path so tests can import 'calculator'
if current_dir not in sys.path:
    sys.path.insert(0, current_dir)


from src.engine import MiniCoverage


def main():
    print(f"Running tests with coverage in: {current_dir}")

    # 2. initialize Coverage for this folder
    cov = MiniCoverage(project_root=current_dir)
    cov.start()

    try:
        # 3. run tests
        loader = unittest.TestLoader()
        suite = loader.discover(current_dir, pattern='test_*.py')
        runner = unittest.TextTestRunner(verbosity=2)
        runner.run(suite)
    finally:
        cov.stop()

    # 4. generate report
    print("\n--- Coverage Report ---")
    cov.report()


if __name__ == "__main__":
    main()
