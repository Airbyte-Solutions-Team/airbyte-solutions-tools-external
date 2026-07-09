"""Airbyte source construction helpers."""

from __future__ import annotations

from typing import Any

from airbyte_cdk.models import ConfiguredAirbyteCatalog
from airbyte_cdk.sources.declarative.concurrent_declarative_source import (
    ConcurrentDeclarativeSource,
)


INJECTED_MANIFEST_KEY = "__injected_declarative_manifest"


def build_source(
    manifest: dict[str, Any],
    config: dict[str, Any],
    catalog: ConfiguredAirbyteCatalog,
    state: list[dict[str, Any]],
) -> ConcurrentDeclarativeSource:
    source_config = dict(config)
    source_config[INJECTED_MANIFEST_KEY] = manifest
    return ConcurrentDeclarativeSource(
        config=source_config,
        catalog=catalog,
        state=state,
        source_config=manifest,
    )

