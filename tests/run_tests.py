import unittest
import os
import sys


def run_all_tests() -> None:
    """
    Discover and run all tests in the current directory.
    """
    # Ensure the project root is in sys.path so src imports work
    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    if project_root not in sys.path:
        sys.path.insert(0, project_root)

    print(f"Running tests from: {os.path.dirname(__file__)}")
    print(f"Project root: {project_root}")
    print("-" * 70)

    loader = unittest.TestLoader()
    start_dir = os.path.dirname(__file__)
    suite = loader.discover(start_dir, pattern="test_*.py")

    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)

    if not result.wasSuccessful():
        sys.exit(1)


if __name__ == "__main__":
    run_all_tests()
