"""Load and validate the YAML configuration file."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Optional

import yaml


class ConfigError(RuntimeError):
    pass


CLOUD_PUBLIC_API_ROOT = "https://api.airbyte.com/v1"
CLOUD_CONFIG_API_ROOT = "https://cloud.airbyte.com/api"


@dataclass(frozen=True)
class EnvironmentConfig:
    public_api_root: str
    config_api_root: str
    workspace_id: str
    client_id: str
    client_secret: str


@dataclass(frozen=True)
class Options:
    output_dir: str = "./migration-output"
    connection_names_file: Optional[str] = None
    export_file: Optional[str] = None
    dry_run: bool = False
    allow_overwrite: bool = False
    use_internal_list: bool = False
    log_level: str = "INFO"


@dataclass(frozen=True)
class Config:
    source: Optional[EnvironmentConfig]
    target: Optional[EnvironmentConfig]
    options: Options


_REQUIRED_ENV_FIELDS = (
    "public_api_root",
    "config_api_root",
    "workspace_id",
    "client_id",
    "client_secret",
)

_VALID_LOG_LEVELS = {"DEBUG", "INFO", "WARNING", "ERROR"}


def load_config(path: str) -> Config:
    try:
        with open(path, "r", encoding="utf-8") as f:
            raw = yaml.safe_load(f)
    except FileNotFoundError:
        raise ConfigError(f"Config file not found: {path}")
    except yaml.YAMLError as exc:
        raise ConfigError(f"Failed to parse YAML at {path}: {exc}")

    if not isinstance(raw, dict):
        raise ConfigError("Config root must be a YAML mapping.")

    return Config(
        source=_parse_env(raw.get("source"), "source"),
        target=_parse_env(
            raw.get("target"),
            "target",
            defaults={
                "public_api_root": CLOUD_PUBLIC_API_ROOT,
                "config_api_root": CLOUD_CONFIG_API_ROOT,
            },
        ),
        options=_parse_options(raw.get("options")),
    )


def _parse_env(
    value: Any,
    label: str,
    defaults: Optional[Dict[str, str]] = None,
) -> Optional[EnvironmentConfig]:
    """Parse one environment section, returning None if it's absent.

    If the section is present, every required field must be set (defaults
    are applied first for any caller-provided defaults, then the merged
    result is checked).
    """
    if value is None:
        return None
    if not isinstance(value, dict):
        raise ConfigError(f"'{label}' section must be a mapping.")

    merged: Dict[str, Any] = dict(defaults or {})
    for k, v in value.items():
        if v is not None:
            merged[k] = v

    missing = [k for k in _REQUIRED_ENV_FIELDS if not merged.get(k)]
    if missing:
        raise ConfigError(f"'{label}' section missing required field(s): {missing}")

    return EnvironmentConfig(**{k: str(merged[k]) for k in _REQUIRED_ENV_FIELDS})


def _parse_options(value: Any) -> Options:
    if value is None:
        value = {}
    if not isinstance(value, dict):
        raise ConfigError("'options' section must be a mapping.")

    log_level = str(value.get("log_level", "INFO")).upper()
    if log_level not in _VALID_LOG_LEVELS:
        raise ConfigError(
            f"options.log_level={log_level!r} is invalid; expected one of {sorted(_VALID_LOG_LEVELS)}"
        )

    return Options(
        output_dir=str(value.get("output_dir", "./migration-output")),
        connection_names_file=_optional_str(value.get("connection_names_file")),
        export_file=_optional_str(value.get("export_file")),
        dry_run=_as_bool(value.get("dry_run"), "options.dry_run"),
        allow_overwrite=_as_bool(value.get("allow_overwrite"), "options.allow_overwrite"),
        use_internal_list=_as_bool(value.get("use_internal_list"), "options.use_internal_list"),
        log_level=log_level,
    )


def _optional_str(value: Any) -> Optional[str]:
    if value is None:
        return None
    return str(value)


def _as_bool(value: Any, field: str) -> bool:
    if value is None:
        return False
    if isinstance(value, bool):
        return value
    raise ConfigError(f"{field} must be a boolean (got {type(value).__name__}).")


def require_source(cfg: Config) -> EnvironmentConfig:
    if cfg.source is None:
        raise ConfigError(
            "Config is missing the 'source' section, which is required for `export`."
        )
    return cfg.source


def require_target(cfg: Config) -> EnvironmentConfig:
    if cfg.target is None:
        raise ConfigError(
            "Config is missing the 'target' section, which is required for `apply`."
        )
    return cfg.target


def require_connection_names_file(cfg: Config) -> str:
    if not cfg.options.connection_names_file:
        raise ConfigError(
            "options.connection_names_file is required for `export`."
        )
    return cfg.options.connection_names_file


def resolve_export_file(cfg: Config) -> str:
    """Return the configured export file path, or the default inside output_dir."""
    if cfg.options.export_file:
        return cfg.options.export_file
    import os
    return os.path.join(cfg.options.output_dir, "state_export.json")
