"""End-to-end orchestration for state migration.

The migration is split into two independent steps:

  - ``run_export`` pulls source state and writes a JSON file keyed by
    connection name.
  - ``run_apply`` reads that JSON file and writes state to the target.

Splitting the flow removes the need for an in-process Terraform pause:
operators run ``export``, apply Terraform at their leisure, then run
``apply`` when they're ready.
"""

from __future__ import annotations

import datetime as dt
import json
import logging
import os
from typing import Any, Dict, List

from .audit import AuditEntry, AuditLog
from .auth import ClientCredentials, fetch_access_token
from .clients import ApiError, ConfigApiClient, PublicApiClient
from .config import (
    Config,
    ConfigError,
    EnvironmentConfig,
    require_connection_names_file,
    require_source,
    require_target,
    resolve_export_file,
)
from .connections import (
    ConnectionValidationError,
    build_name_map,
    connection_id,
    validate_expected,
)
from .io_utils import ensure_output_dir, read_connection_names, write_json
from .state import (
    StateValidationError,
    build_target_payload,
    is_target_writable,
    validate_state_response,
)


log = logging.getLogger("airbyte_state.migrate")

EXPORT_SCHEMA_VERSION = 1

# Airbyte's ConnectionStatus enum is `active | inactive | deprecated | locked`.
# Only `active` is unsafe to write to (a sync could be running). The other
# three are all non-running and accept state writes.
_SAFE_TARGET_STATUSES = {"inactive", "deprecated", "locked"}
_UNUSUAL_TARGET_STATUSES = {"deprecated", "locked"}


class MigrationFailed(RuntimeError):
    pass


class ExportFileError(RuntimeError):
    pass


class _Environment:
    """Bundle of clients for one workspace, with an access token already fetched."""

    def __init__(self, env: EnvironmentConfig, label: str):
        self.label = label
        self.workspace_id = env.workspace_id
        self.public_api_root = env.public_api_root
        self.config_api_root = env.config_api_root
        log.info("Exchanging %s credentials for an access token", label)
        token = fetch_access_token(
            env.public_api_root,
            ClientCredentials(client_id=env.client_id, client_secret=env.client_secret),
        )
        self.public = PublicApiClient(env.public_api_root, token)
        self.config = ConfigApiClient(env.config_api_root, token)


# ---------------------------------------------------------------------------
# export
# ---------------------------------------------------------------------------


def run_export(cfg: Config) -> Dict[str, Any]:
    """Fetch source state for every expected connection and write the export JSON.

    Returns the in-memory export document (also written to disk).
    """
    source_env = require_source(cfg)
    names_file = require_connection_names_file(cfg)
    ensure_output_dir(cfg.options.output_dir)

    log.info("Reading expected connection names from %s", names_file)
    expected_names = read_connection_names(names_file)
    log.info("Expected %d unique connection(s)", len(expected_names))

    source = _Environment(source_env, "source")

    log.info("Listing source workspace connections")
    source_conns = _list_connections(source, cfg.options.use_internal_list)
    source_map = build_name_map(source_conns, expected_names, workspace_label="source")
    validate_expected(expected_names, source_map, workspace_label="source")

    log.info("Fetching source state for %d connection(s)", len(expected_names))
    connections_payload: Dict[str, Dict[str, Any]] = {}
    for name in expected_names:
        cid = connection_id(source_map[name])
        log.info("  -> %s (%s)", name, cid)
        state = source.config.get_state(cid)
        state_type = validate_state_response(name, state)
        connections_payload[name] = {
            "source_connection_id": cid,
            "state_type": state_type,
            "state": state,
            "exported_at": _iso_now(),
        }

    export_doc: Dict[str, Any] = {
        "schema_version": EXPORT_SCHEMA_VERSION,
        "metadata": {
            "exported_at": _iso_now(),
            "source_workspace_id": source.workspace_id,
            "source_public_api_root": source.public_api_root,
            "source_config_api_root": source.config_api_root,
            "connection_count": len(connections_payload),
        },
        "connections": connections_payload,
    }

    export_path = resolve_export_file(cfg)
    ensure_output_dir(os.path.dirname(export_path) or ".")
    write_json(export_path, export_doc)
    log.info("Wrote export file: %s (%d connection(s))", export_path, len(connections_payload))
    return export_doc


# ---------------------------------------------------------------------------
# apply
# ---------------------------------------------------------------------------


def run_apply(cfg: Config) -> AuditLog:
    """Read the export JSON and write each state payload to its target connection."""
    target_env = require_target(cfg)
    export_path = resolve_export_file(cfg)
    ensure_output_dir(cfg.options.output_dir)

    log.info("Reading export file: %s", export_path)
    export_doc = _load_export_file(export_path)
    connections_payload: Dict[str, Dict[str, Any]] = export_doc["connections"]
    expected_names = list(connections_payload.keys())
    log.info("Export file contains %d connection(s)", len(expected_names))

    target = _Environment(target_env, "target")

    log.info("Listing target workspace connections")
    target_conns = _list_connections(target, cfg.options.use_internal_list)
    target_map = build_name_map(target_conns, expected_names, workspace_label="target")
    validate_expected(expected_names, target_map, workspace_label="target")

    log.info(
        "Writing state to target workspace (dry_run=%s, allow_overwrite=%s)",
        cfg.options.dry_run,
        cfg.options.allow_overwrite,
    )

    audit = AuditLog()
    for name in expected_names:
        entry_data = connections_payload[name]
        source_state = entry_data["state"]
        target_record = target_map[name]
        target_cid = connection_id(target_record)
        entry = AuditEntry(
            connection_name=name,
            source_connection_id=entry_data.get("source_connection_id", ""),
            target_connection_id=target_cid,
            source_state_type=entry_data.get("state_type", ""),
        )

        try:
            _ensure_target_safe_for_write(name, target_record)
            _apply_single(
                cfg=cfg,
                target_config=target.config,
                source_state=source_state,
                target_cid=target_cid,
                entry=entry,
            )
        except (ApiError, StateValidationError, ConnectionValidationError) as exc:
            entry.write_status = "failed"
            entry.error = str(exc)
            log.error("  ! %s: %s", name, exc)

        audit.add(entry)

    audit.write(os.path.join(cfg.options.output_dir, "state_write_audit.csv"))

    failures = [e for e in audit.entries if e.write_status == "failed"]
    log.info(
        "Done. written=%d dry_run=%d skipped=%d failed=%d",
        sum(1 for e in audit.entries if e.write_status == "written"),
        sum(1 for e in audit.entries if e.write_status == "dry_run"),
        sum(1 for e in audit.entries if e.write_status == "skipped"),
        len(failures),
    )
    if failures:
        raise MigrationFailed(f"{len(failures)} connection(s) failed; see audit log.")
    return audit


def _ensure_target_safe_for_write(name: str, target_record: Dict[str, Any]) -> None:
    """Refuse to write state to a connection that is currently running.

    Writing state to an `active` connection risks racing the next sync, which
    could read partial / mid-write state and produce undesirable results. The
    connection's `status` field (already returned by the workspace listing)
    tells us whether it's safe to touch.
    """
    status = target_record.get("status")
    if status == "active":
        raise ConnectionValidationError(
            f"Target connection {name!r} has status 'active'. Disable or pause "
            "the connection in Airbyte before applying state to avoid writing "
            "during a running sync."
        )
    if status in _SAFE_TARGET_STATUSES:
        if status in _UNUSUAL_TARGET_STATUSES:
            log.warning(
                "Target connection %r has status %r; writing state but the "
                "connection will not sync in this state.",
                name, status,
            )
        return
    raise ConnectionValidationError(
        f"Target connection {name!r} has unrecognized status {status!r}; "
        f"refusing to write. Expected one of: active, inactive, deprecated, locked."
    )


def _apply_single(
    cfg: Config,
    target_config: ConfigApiClient,
    source_state: Dict[str, Any],
    target_cid: str,
    entry: AuditEntry,
) -> None:
    state_type = source_state.get("stateType")

    if state_type == "not_set":
        entry.write_status = "skipped"
        entry.error = "source stateType is not_set; skipping per brief default"
        log.info("  - %s: skipped (not_set)", entry.connection_name)
        return

    if not cfg.options.allow_overwrite:
        existing = target_config.get_state(target_cid)
        if not is_target_writable(existing):
            raise StateValidationError(
                f"Target connection {entry.connection_name!r} already has non-empty state "
                f"(stateType={existing.get('stateType')!r}); refuse to overwrite. "
                "Set options.allow_overwrite=true to proceed."
            )

    target_payload = build_target_payload(source_state, target_cid)

    if cfg.options.dry_run:
        entry.write_status = "dry_run"
        log.info(
            "  ~ %s: dry_run would write stateType=%s to %s",
            entry.connection_name,
            state_type,
            target_cid,
        )
        return

    target_config.create_or_update_state_safe(target_cid, target_payload)
    entry.write_status = "written"
    log.info("  ✓ %s: wrote stateType=%s to %s", entry.connection_name, state_type, target_cid)


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


def _load_export_file(path: str) -> Dict[str, Any]:
    try:
        with open(path, "r", encoding="utf-8") as f:
            doc = json.load(f)
    except FileNotFoundError:
        raise ExportFileError(
            f"Export file not found: {path}. Run `export` first, or set options.export_file."
        )
    except json.JSONDecodeError as exc:
        raise ExportFileError(f"Export file {path} is not valid JSON: {exc}")

    if not isinstance(doc, dict):
        raise ExportFileError(f"Export file {path} must be a JSON object at the root.")

    version = doc.get("schema_version")
    if version != EXPORT_SCHEMA_VERSION:
        raise ExportFileError(
            f"Export file schema_version {version!r} does not match expected "
            f"{EXPORT_SCHEMA_VERSION}. The file may be from a different tool version."
        )

    connections = doc.get("connections")
    if not isinstance(connections, dict) or not connections:
        raise ExportFileError(
            f"Export file {path} has no 'connections' object, or it is empty."
        )

    return doc


def _list_connections(env: _Environment, use_internal: bool) -> List[Dict[str, Any]]:
    if use_internal:
        return env.config.list_connections(env.workspace_id)
    return env.public.list_connections(env.workspace_id)


def _iso_now() -> str:
    return dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
