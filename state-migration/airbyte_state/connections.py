"""Connection name -> ID resolution and validation."""

from __future__ import annotations

import logging
from typing import Any, Dict, Iterable, List, Sequence


log = logging.getLogger("airbyte_state.connections")


class ConnectionValidationError(RuntimeError):
    pass


def build_name_map(
    connections: Sequence[Dict[str, Any]],
    expected_names: Iterable[str],
    workspace_label: str,
) -> Dict[str, Dict[str, Any]]:
    """Return {name: connection} restricted to names we can resolve unambiguously.

    Workspace listings can legitimately contain unrelated stale duplicates.
    Those don't block work, but they do mean we can't pick "the" record for
    that name. So:

      - If a duplicated name IS in `expected_names`, raise — we cannot
        disambiguate which connection the operator meant. The error lists the
        offending `connectionId`s so the operator can clean them up in Airbyte.
      - If a duplicated name is NOT in `expected_names`, log a warning and
        omit the name from the returned map. Downstream `validate_expected`
        only checks expected names, so unrelated duplicates won't block.
      - Unique names are included as usual.
    """
    expected_set = set(expected_names)

    grouped: Dict[str, List[Dict[str, Any]]] = {}
    for c in connections:
        name = c.get("name")
        if not name:
            continue
        grouped.setdefault(name, []).append(c)

    blocking: List[str] = []
    name_map: Dict[str, Dict[str, Any]] = {}

    for name, records in grouped.items():
        if len(records) == 1:
            name_map[name] = records[0]
            continue

        ids = [_safe_connection_id(r) for r in records]
        if name in expected_set:
            blocking.append(f"{name!r}: connectionIds={ids}")
        else:
            log.warning(
                "Ignoring %d duplicate %s-workspace connection(s) named %r "
                "(connectionIds=%s); not in expected list.",
                len(records), workspace_label, name, ids,
            )

    if blocking:
        detail = "\n  - " + "\n  - ".join(blocking)
        raise ConnectionValidationError(
            f"Connection name(s) appear multiple times in the {workspace_label} "
            f"workspace and are in your expected names list — cannot "
            f"disambiguate:{detail}"
        )

    return name_map


def validate_expected(
    expected_names: Sequence[str],
    name_map: Dict[str, Dict[str, Any]],
    workspace_label: str,
) -> None:
    """Fail if any expected name is missing from the resolved workspace map."""
    missing = sorted(set(expected_names) - set(name_map))
    if missing:
        raise ConnectionValidationError(
            f"Connections expected but not found in {workspace_label} workspace: {missing}"
        )


def connection_id(connection: Dict[str, Any]) -> str:
    """Pull the connectionId out of a connection record, regardless of API source.

    PyAirbyte returns `connectionId`; older internal API records may return
    `connection_id`.
    """
    for key in ("connectionId", "connection_id"):
        value = connection.get(key)
        if value:
            return value
    raise ConnectionValidationError(
        f"Connection record missing connectionId field: {connection.get('name')!r}"
    )


def _safe_connection_id(connection: Dict[str, Any]) -> str:
    for key in ("connectionId", "connection_id"):
        value = connection.get(key)
        if value:
            return value
    return "<unknown>"
