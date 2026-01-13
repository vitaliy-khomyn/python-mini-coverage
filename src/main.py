import argparse
import sys
import os
import logging

from .engine import MiniCoverage


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format='[%(levelname)s] %(message)s',
        stream=sys.stdout
    )

    parser = argparse.ArgumentParser(
        prog="minicov",
        description="A minimalist code coverage tool."
    )
    subparsers = parser.add_subparsers(dest="command", help="Command to execute", required=True)

    # command: run
    parser_run = subparsers.add_parser("run", help="Run a Python program and measure code coverage.")
    parser_run.add_argument("script", help="Python script to execute.")
    parser_run.add_argument("script_args", nargs=argparse.REMAINDER, help="Arguments for the script.")
    parser_run.add_argument("--preserve", action="store_true", help="Preserve existing coverage data (do not delete).")

    # command: report
    parser_report = subparsers.add_parser("report", help="Report coverage results.")
    parser_report.add_argument("--format", nargs="+", choices=['console', 'html', 'xml', 'json'],
                               help="Specify output formats (console, html, xml, json). Default: console html")

    # command: combine
    _ = subparsers.add_parser("combine", help="Combine data from multiple run files.")

    args = parser.parse_args()

    # Determine config file based on command
    config_file = None
    if args.command == "run":
        script_path = args.script
        if os.path.isfile(script_path):
            script_dir = os.path.dirname(os.path.abspath(script_path))
            for config_name in ['.coveragerc', 'pyproject.toml', 'setup.cfg', 'tox.ini']:
                candidate = os.path.join(script_dir, config_name)
                if os.path.exists(candidate):
                    config_file = candidate
                    logging.info(f"Auto-loading local configuration from {config_file}")
                    break

    # determine if we should erase old data (default: True for 'run', unless --preserve is set)
    erase_on_start = False
    if args.command == "run" and not getattr(args, 'preserve', False):
        erase_on_start = True

    # init engine (loads config internally)
    cov = MiniCoverage(config_file=config_file, erase_on_start=erase_on_start)

    if args.command == "run":
        # ensure the script path is absolute or correct relatively to CWD
        script_path = args.script
        if not os.path.isfile(script_path):
            logging.error(f"Script '{script_path}' not found.")
            sys.exit(1)

        cov.run(script_path, args.script_args)

    elif args.command == "report":
        cov.report(reporters=args.format)

    elif args.command == "combine":
        cov.combine_data()
        logging.info("Coverage data combined.")


if __name__ == "__main__":
    main()
