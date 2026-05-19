"""Audit log entry shape and serialization."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List

from .io_utils import write_csv


AUDIT_FIELDS = [
    "connection_name",
    "source_connection_id",
    "target_connection_id",
    "source_state_type",
    "write_status",
    "error",
]


@dataclass
class AuditEntry:
    connection_name: str
    source_connection_id: str = ""
    target_connection_id: str = ""
    source_state_type: str = ""
    write_status: str = ""  # written | dry_run | skipped | failed
    error: str = ""


@dataclass
class AuditLog:
    entries: List[AuditEntry] = field(default_factory=list)

    def add(self, entry: AuditEntry) -> None:
        self.entries.append(entry)

    def to_rows(self) -> List[Dict[str, Any]]:
        return [asdict(e) for e in self.entries]

    def write(self, csv_path: str) -> None:
        write_csv(csv_path, self.to_rows(), AUDIT_FIELDS)
