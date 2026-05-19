"""Reading the expected-connection-names input file and writing output files.

The names file is plain newline-separated text. Each non-empty, non-comment
line is one connection name. The reader enforces uniqueness as part of
parsing — duplicates fail loudly with the line numbers they were found at,
before any API calls are made.
"""

from __future__ import annotations

import csv
import json
import os
from typing import Any, Dict, List, Tuple


class InputFormatError(RuntimeError):
    pass


# (name, "line N")
_Entry = Tuple[str, str]


def read_connection_names(path: str) -> List[str]:
    """Read connection names from a newline-separated text file.

    - One name per line.
    - Blank lines and lines starting with ``#`` are ignored.
    - Surrounding whitespace is trimmed.
    - Names must be unique within the file. Duplicates raise
      ``InputFormatError`` with the offending line numbers.
    """
    entries = _read_lines(path)
    if not entries:
        raise InputFormatError(f"Connection-names file is empty: {path}")
    _ensure_unique(entries, path)
    return [name for name, _ in entries]


def _read_lines(path: str) -> List[_Entry]:
    entries: List[_Entry] = []
    with open(path, "r", encoding="utf-8") as f:
        for i, raw in enumerate(f, start=1):
            line = raw.strip()
            if not line or line.startswith("#"):
                continue
            entries.append((line, f"line {i}"))
    return entries


def _ensure_unique(entries: List[_Entry], path: str) -> None:
    first_seen: Dict[str, str] = {}
    duplicates: List[Tuple[str, str, str]] = []  # (name, first_location, dup_location)
    for name, location in entries:
        if name in first_seen:
            duplicates.append((name, first_seen[name], location))
        else:
            first_seen[name] = location

    if not duplicates:
        return

    detail = "\n".join(
        f"  - {name!r} at {dup_loc} (first seen at {first_loc})"
        for name, first_loc, dup_loc in duplicates
    )
    raise InputFormatError(f"Duplicate connection name(s) in {path}:\n{detail}")


def ensure_output_dir(output_dir: str) -> str:
    os.makedirs(output_dir, exist_ok=True)
    return output_dir


def write_json(path: str, data: Any) -> None:
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, sort_keys=False)
        f.write("\n")


def write_csv(path: str, rows: List[Dict[str, Any]], fieldnames: List[str]) -> None:
    with open(path, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow({k: row.get(k, "") for k in fieldnames})
