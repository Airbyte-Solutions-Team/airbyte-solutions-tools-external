"""Convert structured data files between YAML and JSON."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any, TextIO

import yaml


SUPPORTED_FORMATS = {"json", "yaml"}
YAML_SUFFIXES = {".yaml", ".yml"}


def infer_format(path: Path) -> str | None:
    suffix = path.suffix.lower()
    if suffix == ".json":
        return "json"
    if suffix in YAML_SUFFIXES:
        return "yaml"
    return None


def parse_format(value: str | None, path: Path, role: str) -> str:
    if value and value != "auto":
        return value

    inferred = infer_format(path)
    if inferred:
        return inferred

    raise ValueError(f"Could not infer {role} format from {path}. Specify it explicitly.")


def parse_output_format(value: str | None, output: Path | None, input_format: str) -> str:
    if value and value != "auto":
        return value

    if output:
        inferred = infer_format(output)
        if inferred:
            return inferred

    return "json" if input_format == "yaml" else "yaml"


def load_data(path: Path, input_format: str) -> Any:
    raw = path.read_text(encoding="utf-8")
    if input_format == "json":
        return json.loads(raw)
    if input_format == "yaml":
        return yaml.safe_load(raw)
    raise ValueError(f"Unsupported input format: {input_format}")


def dump_data(data: Any, output_format: str, indent: int) -> str:
    if output_format == "json":
        return f"{json.dumps(data, indent=indent, sort_keys=False)}\n"
    if output_format == "yaml":
        return yaml.safe_dump(data, sort_keys=False)
    raise ValueError(f"Unsupported output format: {output_format}")


def write_output(text: str, output: Path | None, stream: TextIO = sys.stdout) -> None:
    if output:
        output.write_text(text, encoding="utf-8")
    else:
        stream.write(text)


def convert_file(
    input_path: Path,
    output_path: Path | None,
    input_format: str | None,
    output_format: str | None,
    indent: int,
) -> None:
    resolved_input_format = parse_format(input_format, input_path, "input")
    resolved_output_format = parse_output_format(
        output_format, output_path, resolved_input_format
    )

    if resolved_input_format not in SUPPORTED_FORMATS:
        raise ValueError(f"Unsupported input format: {resolved_input_format}")
    if resolved_output_format not in SUPPORTED_FORMATS:
        raise ValueError(f"Unsupported output format: {resolved_output_format}")

    data = load_data(input_path, resolved_input_format)
    write_output(dump_data(data, resolved_output_format, indent), output_path)

