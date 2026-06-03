"""PyAirbyte-backed client adapter for the state migration tool."""

from __future__ import annotations

import base64
import logging
import os
from contextlib import contextmanager
from typing import Any, Dict, Iterator, List, Optional

import requests

log = logging.getLogger("airbyte_state.clients")


class ApiError(RuntimeError):
    def __init__(self, message: str, status: Optional[int] = None, body: Optional[str] = None):
        super().__init__(message)
        self.status = status
        self.body = body


class AirbyteWorkspaceClient:
    """Small adapter over PyAirbyte's CloudWorkspace and CloudConnection APIs."""

    def __init__(
        self,
        api_root: str,
        workspace_id: str,
        client_id: str,
        client_secret: str,
        config_api_root: Optional[str] = None,
    ):
        cloud = _load_cloud_module()
        self.config_api_root = config_api_root.rstrip("/") if config_api_root else None
        try:
            self.workspace = cloud.CloudWorkspace(
                workspace_id=workspace_id,
                client_id=client_id,
                client_secret=client_secret,
                api_root=api_root,
            )
        except Exception as exc:
            raise _api_error("Initialize PyAirbyte CloudWorkspace", exc) from exc

    def list_connections(self, names: Optional[List[str]] = None) -> List[Dict[str, Any]]:
        """Return every connection in the workspace as dicts used by validators."""
        try:
            connections = []
            if names is None:
                connections = self.workspace.list_connections()
            else:
                for name in names:
                    connections.extend(self.workspace.list_connections(name=name))
            return [_connection_record(c) for c in connections]
        except Exception as exc:
            raise _api_error("List connections", exc) from exc

    def get_state(self, connection_id: str) -> Dict[str, Any]:
        try:
            connection = self.workspace.get_connection(connection_id)
            with _config_api_root(self.config_api_root):
                state = connection.dump_raw_state(normalize=False)
        except Exception as exc:
            raise _api_error(f"Dump state for connection {connection_id}", exc) from exc

        if not isinstance(state, dict):
            raise ApiError(
                f"PyAirbyte returned {type(state).__name__} for raw state; expected dict."
            )
        return state

    def import_state(self, connection_id: str, connection_state: Dict[str, Any]) -> Dict[str, Any]:
        try:
            connection = self.workspace.get_connection(connection_id)
            with _config_api_root(self.config_api_root):
                result = connection.import_raw_state(connection_state)
        except Exception as exc:
            raise _api_error(f"Import state for connection {connection_id}", exc) from exc

        if isinstance(result, dict):
            return result
        return {}


def _load_cloud_module() -> Any:
    try:
        from airbyte import cloud
    except ImportError as exc:
        raise ApiError(
            "PyAirbyte is required for state migration. Install dependencies with "
            "`pip install -r requirements.txt` from the state-migration directory."
        ) from exc
    return cloud


@contextmanager
def _config_api_root(config_api_root: Optional[str]) -> Iterator[None]:
    env_var = "AIRBYTE_CLOUD_CONFIG_API_URL"
    previous = os.environ.get(env_var)
    if config_api_root:
        os.environ[env_var] = config_api_root
    try:
        yield
    finally:
        if previous is None:
            os.environ.pop(env_var, None)
        else:
            os.environ[env_var] = previous


def _connection_record(connection: Any) -> Dict[str, Any]:
    status = _connection_status(connection)
    return {
        "name": connection.name,
        "connectionId": connection.connection_id,
        "status": status,
    }


def _connection_status(connection: Any) -> str:
    connection_info = getattr(connection, "_connection_info", None)
    status = _enum_value(getattr(connection_info, "status", None))
    if status:
        return status

    try:
        return "active" if connection.enabled else "inactive"
    except Exception:
        return ""


def _enum_value(value: Any) -> str:
    if value is None:
        return ""
    raw = getattr(value, "value", value)
    text = str(raw).lower()
    if "." in text:
        text = text.rsplit(".", 1)[-1]
    return text


def _api_error(context: str, exc: Exception) -> ApiError:
    status = getattr(exc, "status", None) or getattr(exc, "status_code", None)
    body = getattr(exc, "body", None) or getattr(exc, "response_text", None)
    detail = str(exc)
    if status:
        return ApiError(f"{context} failed: {status} ({detail})", status=status, body=body)
    return ApiError(f"{context} failed: {detail}", body=body)


class LegacyAirbyteClient:
    """Direct HTTP client for Airbyte OSS instances using Basic Auth.

    Targets the internal Config API (POST /api/v1/...) which is the only
    API available on older Airbyte OSS versions (pre-0.63).
    """

    def __init__(
        self,
        config_api_root: str,
        workspace_id: str,
        basic_auth_username: str,
        basic_auth_password: str,
    ):
        self.config_api_root = config_api_root.rstrip("/")
        self.workspace_id = workspace_id
        credentials = f"{basic_auth_username}:{basic_auth_password}"
        encoded = base64.b64encode(credentials.encode()).decode()
        self._headers = {
            "Content-Type": "application/json",
            "Authorization": f"Basic {encoded}",
        }
        self._session = requests.Session()
        self._session.headers.update(self._headers)

    def _post(self, path: str, body: Dict[str, Any]) -> Dict[str, Any]:
        url = f"{self.config_api_root}/{path.lstrip('/')}"
        log.debug("POST %s", url)
        try:
            resp = self._session.post(url, json=body, timeout=60)
        except requests.RequestException as exc:
            raise ApiError(f"Request to {url} failed: {exc}") from exc

        if resp.status_code >= 400:
            raise ApiError(
                f"POST {path} returned {resp.status_code}",
                status=resp.status_code,
                body=resp.text,
            )
        return resp.json()

    def list_connections(self, names: Optional[List[str]] = None) -> List[Dict[str, Any]]:
        """List connections in the workspace via the Config API."""
        payload: Dict[str, Any] = {"workspaceId": self.workspace_id}
        data = self._post("connections/list", payload)
        connections = data.get("connections", [])

        records = []
        for conn in connections:
            record = {
                "name": conn.get("name", ""),
                "connectionId": conn.get("connectionId", ""),
                "status": (conn.get("status") or "").lower(),
            }
            records.append(record)

        if names is not None:
            name_set = set(names)
            records = [r for r in records if r["name"] in name_set]

        return records

    def get_state(self, connection_id: str) -> Dict[str, Any]:
        """Fetch connection state via POST /state/get."""
        data = self._post("state/get", {"connectionId": connection_id})
        if not isinstance(data, dict):
            raise ApiError(
                f"Config API returned {type(data).__name__} for state; expected dict."
            )
        return data

    def import_state(self, connection_id: str, connection_state: Dict[str, Any]) -> Dict[str, Any]:
        """Write connection state via POST /state/create_or_update.

        The Config API expects a `ConnectionStateCreateOrUpdate` envelope with
        `connectionId` at the top level and the state nested under `connectionState`.
        """
        body = {
            "connectionId": connection_id,
            "connectionState": {
                **connection_state,
                "connectionId": connection_id,
            },
        }
        data = self._post("state/create_or_update", body)
        if isinstance(data, dict):
            return data
        return {}
