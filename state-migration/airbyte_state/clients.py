"""HTTP clients for the Airbyte public and Config APIs.

Both clients accept a pre-fetched bearer access token. The same token from
the client-credentials exchange works for both APIs.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

import requests


class ApiError(RuntimeError):
    def __init__(self, message: str, status: Optional[int] = None, body: Optional[str] = None):
        super().__init__(message)
        self.status = status
        self.body = body


def _bearer_headers(access_token: str) -> Dict[str, str]:
    return {
        "Authorization": f"Bearer {access_token}",
        "Accept": "application/json",
        "Content-Type": "application/json",
    }


class PublicApiClient:
    """Thin wrapper around the Airbyte public API.

    Only the endpoints required for state migration are implemented.
    """

    def __init__(self, public_api_root: str, access_token: str, timeout: int = 30):
        self.root = public_api_root.rstrip("/")
        self.timeout = timeout
        self.session = requests.Session()
        self.session.headers.update(_bearer_headers(access_token))

    def list_connections(self, workspace_id: str, page_size: int = 100) -> List[Dict[str, Any]]:
        """Return every connection in a workspace, paginating until exhausted."""
        offset = 0
        results: List[Dict[str, Any]] = []
        while True:
            params = {
                "workspaceIds": workspace_id,
                "limit": page_size,
                "offset": offset,
            }
            response = self.session.get(
                f"{self.root}/connections", params=params, timeout=self.timeout
            )
            _raise_for_status(response, context="GET /connections")
            payload = response.json() or {}
            page = payload.get("data") or []
            results.extend(page)
            if len(page) < page_size:
                break
            offset += page_size
        return results


class ConfigApiClient:
    """Thin wrapper around the non-public Airbyte Config API."""

    def __init__(self, config_api_root: str, access_token: str, timeout: int = 60):
        self.root = config_api_root.rstrip("/")
        self.timeout = timeout
        self.session = requests.Session()
        self.session.headers.update(_bearer_headers(access_token))

    def list_connections(self, workspace_id: str) -> List[Dict[str, Any]]:
        """Internal fallback for listing connections by workspace."""
        response = self.session.post(
            f"{self.root}/v1/connections/list",
            json={"workspaceId": workspace_id},
            timeout=self.timeout,
        )
        _raise_for_status(response, context="POST /v1/connections/list")
        payload = response.json() or {}
        return payload.get("connections") or []

    def get_state(self, connection_id: str) -> Dict[str, Any]:
        response = self.session.post(
            f"{self.root}/v1/state/get",
            json={"connectionId": connection_id},
            timeout=self.timeout,
        )
        _raise_for_status(response, context="POST /v1/state/get")
        return response.json() or {}

    def create_or_update_state_safe(
        self, connection_id: str, connection_state: Dict[str, Any]
    ) -> Dict[str, Any]:
        body = {
            "connectionId": connection_id,
            "connectionState": connection_state,
        }
        response = self.session.post(
            f"{self.root}/v1/state/create_or_update_safe",
            json=body,
            timeout=self.timeout,
        )
        _raise_for_status(response, context="POST /v1/state/create_or_update_safe")
        return response.json() or {}


def _raise_for_status(response: requests.Response, context: str) -> None:
    if response.ok:
        return
    body = (response.text or "")[:1000]
    raise ApiError(
        f"{context} failed: {response.status_code} {response.reason} (body: {body})",
        status=response.status_code,
        body=body,
    )
