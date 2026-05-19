#!/usr/bin/env python3
"""CLI entry point for the Airbyte connection state migration tool.

All configuration lives in a YAML file. See `config.example.yaml` and
`README.md` for the expected shape.
"""

from __future__ import annotations

import argparse
import logging
import sys

from airbyte_state.clients import ApiError
from airbyte_state.config import ConfigError, load_config
from airbyte_state.connections import ConnectionValidationError
from airbyte_state.io_utils import InputFormatError
from airbyte_state.migrate import (
    ExportFileError,
    MigrationFailed,
    run_apply,
    run_export,
)
from airbyte_state.state import StateValidationError


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Migrate Airbyte connection state from one workspace to another."
    )
    subparsers = parser.add_subparsers(dest="command", required=True, metavar="COMMAND")

    export_parser = subparsers.add_parser(
        "export",
        help="Pull source state and write it to a JSON file keyed by connection name.",
    )
    _add_config_flag(export_parser)

    apply_parser = subparsers.add_parser(
        "apply",
        help="Read the export JSON and write state to the target workspace.",
    )
    _add_config_flag(apply_parser)

    return parser


def _add_config_flag(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--config",
        "-c",
        default="config.yaml",
        help="Path to YAML config file (default: config.yaml).",
    )


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)

    try:
        cfg = load_config(args.config)
    except ConfigError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    logging.basicConfig(
        level=cfg.options.log_level,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    try:
        if args.command == "export":
            run_export(cfg)
        elif args.command == "apply":
            run_apply(cfg)
        else:  # pragma: no cover — argparse rejects unknown commands
            raise ConfigError(f"Unknown command: {args.command!r}")
        return 0
    except (
        ApiError,
        ConfigError,
        ConnectionValidationError,
        StateValidationError,
        InputFormatError,
        ExportFileError,
        MigrationFailed,
    ) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
