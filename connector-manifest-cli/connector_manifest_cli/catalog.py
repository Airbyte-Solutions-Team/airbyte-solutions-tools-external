"""Build Airbyte catalog objects from declarative manifests."""

from __future__ import annotations

from typing import Any

from airbyte_cdk.models import (
    AirbyteStream,
    ConfiguredAirbyteCatalog,
    ConfiguredAirbyteStream,
    DestinationSyncMode,
    SyncMode,
)


def get_manifest_streams(manifest: dict[str, Any]) -> list[dict[str, Any]]:
    streams = manifest.get("streams")
    if not isinstance(streams, list) or not streams:
        raise ValueError("Manifest must contain at least one stream.")

    for index, stream in enumerate(streams, start=1):
        if not isinstance(stream, dict) or not stream.get("name"):
            raise ValueError(f"Stream #{index} must be an object with a name.")

    return streams


def selected_manifest_stream(manifest: dict[str, Any], selected_name: str) -> dict[str, Any]:
    streams = get_manifest_streams(manifest)
    by_name = {stream["name"]: stream for stream in streams}
    if selected_name not in by_name:
        available = ", ".join(sorted(by_name))
        raise ValueError(f"Unknown stream: {selected_name}. Available streams: {available}")

    return by_name[selected_name]


def get_stream_schema(stream: dict[str, Any]) -> dict[str, Any]:
    schema_loader = stream.get("schema_loader", {})
    if isinstance(schema_loader, dict) and isinstance(schema_loader.get("schema"), dict):
        return schema_loader["schema"]

    return {}


def get_primary_key(stream: dict[str, Any]) -> list[list[str]] | None:
    primary_key = stream.get("primary_key")
    if not primary_key:
        return None

    if isinstance(primary_key, str):
        return [[primary_key]]

    if isinstance(primary_key, list):
        keys = []
        for key in primary_key:
            if isinstance(key, str):
                keys.append([key])
            elif isinstance(key, list) and all(isinstance(part, str) for part in key):
                keys.append(key)
            else:
                raise ValueError(f"Unsupported primary key format for stream {stream['name']}")
        return keys

    raise ValueError(f"Unsupported primary key format for stream {stream['name']}")


def build_configured_catalog(
    manifest: dict[str, Any], selected_name: str
) -> ConfiguredAirbyteCatalog:
    stream = selected_manifest_stream(manifest, selected_name)
    supports_incremental = "incremental_sync" in stream
    sync_mode = SyncMode.incremental if supports_incremental else SyncMode.full_refresh
    supported_sync_modes = [SyncMode.full_refresh]
    if supports_incremental:
        supported_sync_modes.append(SyncMode.incremental)

    airbyte_stream = AirbyteStream(
        name=stream["name"],
        json_schema=get_stream_schema(stream),
        supported_sync_modes=supported_sync_modes,
        default_cursor_field=[stream["incremental_sync"]["cursor_field"]]
        if supports_incremental
        and isinstance(stream.get("incremental_sync"), dict)
        and isinstance(stream["incremental_sync"].get("cursor_field"), str)
        else None,
        source_defined_primary_key=get_primary_key(stream),
    )

    return ConfiguredAirbyteCatalog(
        streams=[
            ConfiguredAirbyteStream(
                stream=airbyte_stream,
                sync_mode=sync_mode,
                destination_sync_mode=DestinationSyncMode.append,
                cursor_field=airbyte_stream.default_cursor_field,
                primary_key=airbyte_stream.source_defined_primary_key,
            )
        ]
    )

