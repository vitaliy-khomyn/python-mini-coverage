import pytest
import os
from ..engine import MiniCoverage

# global instance for the session
_cov_engine = None

def pytest_addoption(parser):
    """Register command line options."""
    group = parser.getgroup("minicov")
    group.addoption(
        "--minicov",
        action="store_true",
        help="Enable MiniCoverage measurement"
    )


def pytest_configure(config):
    """
    Initialize the coverage engine if the flag is set.
    """
    global _cov_engine
    if config.getoption("--minicov"):
        # assume the project root is the pytest rootdir
        root = str(config.rootdir)
        _cov_engine = MiniCoverage(project_root=root)
        _cov_engine.start()


def pytest_sessionfinish(session, exitstatus):
    """
    Stop coverage and save data at the end of the session.
    """
    global _cov_engine
    if _cov_engine:
        _cov_engine.stop()
        # optionally print a small summary or generate a report here
        # _cov_engine.report()
        print("\n[MiniCoverage] Data saved.")
        _cov_engine = None


def pytest_runtest_setup(item):
    """
    Switch context before each test.
    Context ID: file.py::class::test_name (nodeid)
    """
    global _cov_engine
    if _cov_engine:
        _cov_engine.switch_context(item.nodeid)


def pytest_runtest_teardown(item):
    """
    Revert to default context after test.
    """
    global _cov_engine
    if _cov_engine:
        _cov_engine.switch_context("default")
