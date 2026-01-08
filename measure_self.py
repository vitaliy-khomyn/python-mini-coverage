import sys
import os
import unittest
import importlib
import multiprocessing

# ensure the project root is in sys.path so 'src' can be imported
project_root = os.path.dirname(os.path.abspath(__file__))
if project_root not in sys.path:
    sys.path.insert(0, project_root)


from src.engine import MiniCoverage


def main():
    """
    Runs the project's unit tests while measuring code coverage of the 'src' directory.
    """
    # define the directory to measure (the library itself)
    src_dir = os.path.join(project_root, 'src')

    print("--- Starting Self-Coverage Measurement ---")
    print(f"Target Directory: {src_dir}")

    # initialize MiniCoverage
    # explicitly set project_root to 'src' to avoid tracing the tests themselves or standard libs
    cov = MiniCoverage(project_root=src_dir)

    # start tracing
    # note: if the tests themselves instantiate MiniCoverage (e.g. in integration tests),
    # they might conflict if using the same sys.monitoring ID.
    # however, the engine's fallback logic (sys.settrace) usually handles this gracefully.
    cov.start()

    # temporarily unpatch multiprocessing.Process so that when src.engine is reloaded,
    # the new CoverageProcess inherits from the original Process, not the patched one.
    engine_module = sys.modules.get('src.engine.core')
    if engine_module and hasattr(engine_module, '_OriginalProcess'):
        multiprocessing.Process = engine_module._OriginalProcess
        if hasattr(multiprocessing, '_mini_coverage_patched'):
            del multiprocessing._mini_coverage_patched

    # reload 'src' modules to capture top-level definitions (imports, classes, decorators)
    # that were executed before coverage started.
    print("Reloading modules to capture definition coverage...")
    # Snapshot the list of modules to avoid runtime changes during iteration
    modules_to_reload = [
        m for name, m in sys.modules.items()
        if name.startswith('src') and hasattr(m, '__file__')
    ]
    for module in modules_to_reload:
        try:
            importlib.reload(module)
        except Exception as e:
            print(f"Warning: Failed to reload {module.__name__}: {e}")

    # re-patch multiprocessing with the reloaded CoverageProcess class
    # this prevents PicklingError due to class identity mismatch
    engine_module = sys.modules.get('src.engine.core')
    if engine_module and hasattr(engine_module, 'CoverageProcess'):
        multiprocessing.Process = engine_module.CoverageProcess
        # restore config which was reset by reload
        if hasattr(engine_module.CoverageProcess, '_subprocess_setup'):
            engine_module.CoverageProcess._subprocess_setup["project_root"] = cov.project_root
            engine_module.CoverageProcess._subprocess_setup["config_file"] = cov.config_file

    success = False
    try:
        print("Discovering and running tests...")

        # discover tests in the 'tests' directory
        loader = unittest.TestLoader()
        tests_dir = os.path.join(project_root, 'tests')

        if os.path.exists(tests_dir):
            suite = loader.discover(tests_dir)
        else:
            print(f"Warning: 'tests' directory not found at {tests_dir}. Scanning root.")
            suite = loader.discover(project_root)

        # run the tests
        runner = unittest.TextTestRunner(verbosity=2)
        result = runner.run(suite)
        success = result.wasSuccessful()

    except Exception as e:
        print(f"An error occurred during test execution: {e}")
        import traceback
        traceback.print_exc()

    finally:
        # stop tracing and save data
        print("Stopping coverage...")
        cov.stop()

    # generate reports (Console, HTML, JSON)
    print("\n--- Generating Reports ---")
    cov.report(reporters=['console', 'html', 'json'])

    # exit with status code based on test results
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
