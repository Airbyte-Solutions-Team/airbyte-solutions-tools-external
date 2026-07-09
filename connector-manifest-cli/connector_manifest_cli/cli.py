"""Command line interface for connector manifest testing."""

from __future__ import annotations

import argparse
import logging
import sys
from contextlib import ExitStack, nullcontext, redirect_stderr, redirect_stdout
from pathlib import Path
from typing import Any, Sequence

from airbyte_cdk.models import ConfiguredAirbyteCatalog
from airbyte_cdk.sources.declarative.concurrent_declarative_source import (
    ConcurrentDeclarativeSource,
)
from connector_manifest_cli.catalog import build_configured_catalog
from connector_manifest_cli.convert import convert_file
from connector_manifest_cli.errors import print_error
from connector_manifest_cli.formatting import (
    AirbyteStdoutFormatter,
    build_read_logger,
    format_read_message,
    install_human_root_logger,
    message_to_json,
)
from connector_manifest_cli.io_utils import load_json_object, load_state, load_yaml_object
from connector_manifest_cli.schema import (
    accumulate_record_for_schema,
    build_schema_inferrer,
    report_schema_inference,
)
from connector_manifest_cli.source import INJECTED_MANIFEST_KEY, build_source


DEFAULT_MANIFEST = Path("fixtures/test.yaml")
SUBCOMMANDS = {"test", "convert"}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Validate, read, and convert connector manifests."
    )
    subparsers = parser.add_subparsers(dest="command")

    add_test_parser(subparsers)
    add_convert_parser(subparsers)
    return parser


def add_test_parser(subparsers: Any) -> None:
    parser = subparsers.add_parser(
        "test",
        help="Validate and optionally read from a connector manifest.",
    )
    parser.add_argument(
        "--manifest",
        "-m",
        type=Path,
        default=DEFAULT_MANIFEST,
        help=f"Path to the declarative manifest YAML file. Default: {DEFAULT_MANIFEST}",
    )
    parser.add_argument(
        "--stream",
        "-s",
        required=True,
        help="Stream to include in the configured catalog.",
    )
    parser.add_argument(
        "--read",
        action="store_true",
        help="Run source.read after validation. This may call external APIs.",
    )
    parser.add_argument(
        "--json-output",
        action="store_true",
        help="Print raw Airbyte messages as JSON during --read.",
    )
    parser.add_argument(
        "--skip-schema-inference",
        action="store_true",
        help="Do not infer and validate the stream schema after --read.",
    )
    parser.add_argument(
        "--state-file",
        type=Path,
        help="Optional JSON file containing Airbyte state to pass to source.read.",
    )
    parser.add_argument(
        "--log-level",
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"],
        help="Logging level. Default: INFO",
    )
    parser.add_argument(
        "--show-traceback",
        action="store_true",
        help="Print full Python tracebacks for debugging.",
    )

    config_group = parser.add_mutually_exclusive_group()
    config_group.add_argument(
        "--config-json",
        default="{}",
        help="Connector config as a JSON object. Use this for credentials or other connector inputs. Default: '{}'",
    )
    config_group.add_argument(
        "--config-file",
        type=Path,
        help="Path to a JSON file containing connector config.",
    )


def add_convert_parser(subparsers: Any) -> None:
    parser = subparsers.add_parser(
        "convert",
        help="Convert a YAML or JSON file for Terraform or other tooling.",
    )
    parser.add_argument("input", type=Path, help="Input YAML or JSON file.")
    parser.add_argument(
        "--output",
        "-o",
        type=Path,
        help="Output file. Defaults to stdout.",
    )
    parser.add_argument(
        "--from-format",
        choices=["auto", "yaml", "json"],
        default="auto",
        help="Input format. Default: auto.",
    )
    parser.add_argument(
        "--to-format",
        choices=["auto", "json", "yaml"],
        default="auto",
        help="Output format. Default: inferred from output path or opposite input format.",
    )
    parser.add_argument(
        "--indent",
        type=int,
        default=2,
        help="JSON indentation when writing JSON. Default: 2.",
    )
    parser.add_argument(
        "--show-traceback",
        action="store_true",
        help="Print full Python tracebacks for debugging.",
    )


def normalize_argv(argv: Sequence[str] | None) -> list[str]:
    args = list(sys.argv[1:] if argv is None else argv)
    if not args or args[0] in SUBCOMMANDS or args[0] in {"-h", "--help"}:
        return args
    return ["test", *args]


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = build_parser()
    args = parser.parse_args(normalize_argv(argv))
    if not args.command:
        parser.print_help()
        raise SystemExit(0)
    return args


def run_test(args: argparse.Namespace) -> int:
    logging.basicConfig(level=args.log_level)

    manifest = load_yaml_object(args.manifest)
    connector_config = load_json_object(args.config_file, args.config_json)
    state = load_state(args.state_file)

    catalog = build_configured_catalog(manifest, args.stream)
    source = build_source(manifest, connector_config, catalog, state)

    stream_names = ", ".join(stream.stream.name for stream in catalog.streams)
    print(f"Manifest validated OK: {args.manifest} ({stream_names})")

    if not args.read:
        return 0

    return run_read(args, manifest, connector_config, catalog, source, state)


def run_read(
    args: argparse.Namespace,
    manifest: dict[str, Any],
    connector_config: dict[str, Any],
    catalog: ConfiguredAirbyteCatalog,
    source: ConcurrentDeclarativeSource,
    state: list[Any],
) -> int:
    read_config = dict(connector_config)
    read_config[INJECTED_MANIFEST_KEY] = manifest
    read_logger = build_read_logger("local_manifest", args.log_level, args.json_output)
    output_stream = sys.stdout
    schema_inferrer = None if args.skip_schema_inference else build_schema_inferrer(catalog)
    schema_record_count = 0

    with ExitStack() as stack:
        output_formatter = None
        if not args.json_output:
            output_formatter = AirbyteStdoutFormatter(output_stream)
            stack.enter_context(redirect_stdout(output_formatter))
            stack.enter_context(redirect_stderr(output_formatter))
            install_human_root_logger(stack, output_stream, args.log_level)
        else:
            stack.enter_context(nullcontext())

        for message in source.read(
            logger=read_logger,
            config=read_config,
            catalog=catalog,
            state=state,
        ):
            output = message_to_json(message) if args.json_output else format_read_message(message)
            print(output, file=output_stream)
            if schema_inferrer and accumulate_record_for_schema(
                schema_inferrer, message, args.stream
            ):
                schema_record_count += 1

        schema_ok = True
        if schema_inferrer:
            schema_ok = report_schema_inference(
                schema_inferrer,
                args.stream,
                schema_record_count,
                output_stream,
                args.json_output,
            )

        if output_formatter:
            output_formatter.flush()

    return 0 if schema_ok else 1


def run_convert(args: argparse.Namespace) -> int:
    convert_file(
        input_path=args.input,
        output_path=args.output,
        input_format=args.from_format,
        output_format=args.to_format,
        indent=args.indent,
    )
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        if args.command == "test":
            return run_test(args)
        if args.command == "convert":
            return run_convert(args)
        raise ValueError(f"Unknown command: {args.command}")
    except Exception as exc:
        print_error(
            exc,
            sys.stderr,
            json_output=getattr(args, "json_output", False),
            show_traceback=getattr(args, "show_traceback", False),
        )
        return 1
