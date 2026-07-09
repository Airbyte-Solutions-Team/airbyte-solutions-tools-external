"""File loading helpers for the connector manifest CLI."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import yaml


def load_yaml_object(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as file:
        data = yaml.safe_load(file)

    if not isinstance(data, dict):
        raise ValueError(f"YAML file must contain an object: {path}")

    return data


def load_json_object(path: Path | None = None, raw_json: str | None = None) -> dict[str, Any]:
    if path:
        raw_json = path.read_text(encoding="utf-8")

    try:
        data = json.loads(raw_json or "{}")
    except json.JSONDecodeError as exc:
        raise ValueError(f"Connector config must be valid JSON: {exc}") from exc

    if not isinstance(data, dict):
        raise ValueError("Connector config must be a JSON object.")

    return data


def load_state(path: Path | None) -> list[Any]:
    if not path:
        return []

    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"State must be valid JSON: {exc}") from exc

    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        return [data]

    raise ValueError("State must be a JSON object or array.")

