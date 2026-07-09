"""Output formatting helpers for connector manifest reads."""

from __future__ import annotations

import json
import logging
import sys
from contextlib import ExitStack
from dataclasses import asdict, is_dataclass
from typing import Any


def message_to_json(message: Any) -> str:
    if is_dataclass(message):
        return json.dumps(asdict(message), default=str)
    return json.dumps(message, default=str)


def color(text: str, code: str) -> str:
    return f"\033[{code}m{text}\033[0m"


class ColorLogFormatter(logging.Formatter):
    level_colors = {
        "ERROR": "31",
        "WARNING": "33",
        "INFO": "36",
        "DEBUG": "90",
        "CRITICAL": "31",
    }

    def format(self, record: logging.LogRecord) -> str:
        level = record.levelname
        return f"{color(level.ljust(7), self.level_colors.get(level, '37'))} {record.getMessage()}"


class AirbyteStdoutFormatter:
    def __init__(self, stream: Any) -> None:
        self.stream = stream
        self.pending = ""

    def write(self, chunk: str) -> int:
        self.pending += chunk
        while "\n" in self.pending:
            line, self.pending = self.pending.split("\n", 1)
            self._write_line(line)
        return len(chunk)

    def flush(self) -> None:
        if self.pending:
            self._write_line(self.pending)
            self.pending = ""
        self.stream.flush()

    def _write_line(self, line: str) -> None:
        if not line:
            self.stream.write("\n")
            return

        try:
            message = json.loads(line)
        except json.JSONDecodeError:
            self.stream.write(f"{line}\n")
            return

        if isinstance(message, dict) and message.get("type") == "LOG":
            self.stream.write(f"{format_read_message(message)}\n")
        else:
            self.stream.write(f"{line}\n")


def build_read_logger(name: str, level: str, json_output: bool) -> logging.Logger:
    logger = logging.getLogger(name)
    logger.setLevel(level)

    if json_output:
        return logger

    logger.handlers.clear()
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(ColorLogFormatter())
    logger.addHandler(handler)
    logger.propagate = False
    return logger


def install_human_root_logger(stack: ExitStack, stream: Any, level: str) -> None:
    root_logger = logging.getLogger()
    previous_handlers = list(root_logger.handlers)
    previous_level = root_logger.level

    handler = logging.StreamHandler(stream)
    handler.setFormatter(ColorLogFormatter())
    root_logger.handlers = [handler]
    root_logger.setLevel(level)

    def restore() -> None:
        root_logger.handlers = previous_handlers
        root_logger.setLevel(previous_level)

    stack.callback(restore)


def enum_value(value: Any) -> str:
    raw_value = getattr(value, "value", value)
    if isinstance(raw_value, str):
        return raw_value.split(".")[-1]
    return str(raw_value).split(".")[-1]


def field(source: Any, name: str, default: Any = None) -> Any:
    if isinstance(source, dict):
        return source.get(name, default)
    return getattr(source, name, default)


def format_read_message(message: Any) -> str:
    message_type = enum_value(field(message, "type", "MESSAGE"))

    log = field(message, "log")
    if log:
        level = enum_value(field(log, "level", "INFO"))
        message_text = field(log, "message", "")
        level_colors = {
            "ERROR": "31",
            "WARN": "33",
            "WARNING": "33",
            "INFO": "36",
            "DEBUG": "90",
        }
        return f"{color(level.ljust(7), level_colors.get(level, '37'))} {message_text}"

    record = field(message, "record")
    if record:
        stream = field(record, "stream", "unknown")
        data = field(record, "data", {})
        return f"{color('RECORD ', '32')} {stream}: {json.dumps(data, default=str)}"

    state = field(message, "state")
    if state:
        stream_state = field(state, "stream")
        stream = field(field(stream_state, "stream_descriptor"), "name")
        label = f"STATE  {stream}" if stream else "STATE"
        return color(label, "35")

    trace = field(message, "trace")
    if trace:
        trace_type = enum_value(field(trace, "type", "TRACE"))
        stream_status = field(trace, "stream_status")
        if stream_status:
            descriptor = field(stream_status, "stream_descriptor")
            stream = field(descriptor, "name", "unknown")
            status = enum_value(field(stream_status, "status", "unknown"))
            return f"{color('TRACE  ', '34')} {stream}: {status}"
        error = field(trace, "error")
        if error:
            return f"{color('TRACE  ', '31')} {field(error, 'message', error)}"
        return f"{color('TRACE  ', '34')} {trace_type}"

    return f"{color(message_type.ljust(7), '37')} {message_to_json(message)}"


def print_tool_message(
    output_stream: Any,
    label: str,
    text: str,
    color_code: str,
    json_output: bool,
    level: str,
) -> None:
    if json_output:
        print(
            json.dumps({"type": "LOG", "log": {"level": level, "message": text}}),
            file=output_stream,
        )
    else:
        print(f"{color(label.ljust(7), color_code)} {text}", file=output_stream)

