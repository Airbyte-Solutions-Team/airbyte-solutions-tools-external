"""Concise error formatting for CLI output."""

from __future__ import annotations

import json
import traceback
from collections.abc import Iterable
from typing import Any, TextIO

from jsonschema.exceptions import ValidationError

from connector_manifest_cli.formatting import color


def format_path(parts: Iterable[Any]) -> str:
    path = ""
    for part in parts:
        if isinstance(part, int):
            path += f"[{part}]"
        elif path:
            path += f".{part}"
        else:
            path = str(part)
    return path or "<root>"


def compact_validation_error(exc: ValidationError) -> list[str]:
    cause = exc.__cause__ if isinstance(exc.__cause__, ValidationError) else exc
    lines = ["Manifest validation failed"]

    enum_contexts = [
        context
        for context in cause.context
        if context.validator == "enum" and list(context.path) == ["type"]
    ]
    if enum_contexts:
        location = format_path([*cause.path, "type"])
        invalid_type = None
        if isinstance(cause.instance, dict):
            invalid_type = cause.instance.get("type")
        expected_types = [
            expected
            for context in enum_contexts
            for expected in context.validator_value
        ]
        lines.append(f"Location: {location}")
        if invalid_type:
            lines.append(f"Invalid type: {invalid_type}")
        if expected_types:
            lines.append(f"Expected one of: {', '.join(expected_types)}")
        return lines

    lines.append(f"Location: {format_path(cause.path)}")
    lines.append(cause.message)
    return lines


def compact_error_lines(exc: Exception) -> list[str]:
    if isinstance(exc, ValidationError):
        return compact_validation_error(exc)
    if isinstance(exc.__cause__, ValidationError):
        return compact_validation_error(exc.__cause__)
    return [str(exc) or exc.__class__.__name__]


def print_error(
    exc: Exception,
    stream: TextIO,
    *,
    json_output: bool = False,
    show_traceback: bool = False,
) -> None:
    if show_traceback:
        traceback.print_exception(type(exc), exc, exc.__traceback__, file=stream)
        return

    lines = compact_error_lines(exc)
    if json_output:
        for line in lines:
            print(json.dumps({"type": "LOG", "log": {"level": "ERROR", "message": line}}), file=stream)
        return

    print(f"{color('ERROR  ', '31')} {lines[0]}", file=stream)
    for line in lines[1:]:
        print(f"{color('DETAIL ', '33')} {line}", file=stream)

