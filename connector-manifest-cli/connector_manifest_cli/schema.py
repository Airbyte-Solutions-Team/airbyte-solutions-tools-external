"""Schema inference helpers matching Connector Builder validation behavior."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

from airbyte_cdk.models import ConfiguredAirbyteCatalog
from airbyte_cdk.utils.schema_inferrer import SchemaInferrer, SchemaValidationException

from connector_manifest_cli.formatting import field, print_tool_message


def required_paths(value: Any) -> list[list[str]] | None:
    if not value:
        return None
    if isinstance(value, str):
        return [[value]]
    if isinstance(value, list):
        if not value:
            return None
        if all(isinstance(item, str) for item in value):
            return [value]
        if all(
            isinstance(item, list) and all(isinstance(part, str) for part in item)
            for item in value
        ):
            return value

    raise ValueError(f"Unsupported schema inference path: {value}")


def build_schema_inferrer(catalog: ConfiguredAirbyteCatalog) -> SchemaInferrer:
    configured_stream = catalog.streams[0]
    return SchemaInferrer(
        pk=required_paths(configured_stream.primary_key),
        cursor_field=required_paths(configured_stream.cursor_field),
    )


def accumulate_record_for_schema(
    schema_inferrer: SchemaInferrer, message: Any, stream_name: str
) -> bool:
    record = field(message, "record")
    if not record or field(record, "stream") != stream_name:
        return False

    schema_inferrer.accumulate(
        SimpleNamespace(stream=field(record, "stream"), data=field(record, "data", {}))
    )
    return True


def report_schema_inference(
    schema_inferrer: SchemaInferrer,
    stream_name: str,
    record_count: int,
    output_stream: Any,
    json_output: bool,
) -> bool:
    if record_count == 0:
        print_tool_message(
            output_stream,
            "SCHEMA",
            f"Skipped schema inference for {stream_name}: no records were read",
            "33",
            json_output,
            "WARN",
        )
        return True

    try:
        schema_inferrer.get_stream_schema(stream_name)
    except SchemaValidationException as exc:
        print_tool_message(
            output_stream,
            "SCHEMA",
            f"Schema inference failed for {stream_name}",
            "31",
            json_output,
            "ERROR",
        )
        for validation_error in exc.validation_errors:
            print_tool_message(
                output_stream,
                "ERROR",
                validation_error,
                "31",
                json_output,
                "ERROR",
            )
        return False

    print_tool_message(
        output_stream,
        "SCHEMA",
        f"Inferred schema OK for {stream_name} from {record_count} record(s)",
        "32",
        json_output,
        "INFO",
    )
    return True

