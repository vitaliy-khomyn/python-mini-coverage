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

    # command: report
    parser_report = subparsers.add_parser("report", help="Report coverage results.")

    # command: combine
    parser_combine = subparsers.add_parser("combine", help="Combine data from multiple run files.")

    args = parser.parse_args()

    # init engine (loads config internally)
    cov = MiniCoverage()

    if args.command == "run":
        # ensure the script path is absolute or correct relatively to CWD
        script_path = args.script
        if not os.path.isfile(script_path):
            logging.error(f"Script '{script_path}' not found.")
            sys.exit(1)

        cov.run(script_path, args.script_args)

    elif args.command == "report":
        cov.report()

    elif args.command == "combine":
        cov.combine_data()
        logging.info("Coverage data combined.")


if __name__ == "__main__":
    main()
