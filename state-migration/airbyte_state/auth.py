from __future__ import annotations

from dataclasses import dataclass

import requests


class AuthError(RuntimeError):
    pass


@dataclass(frozen=True)
class ClientCredentials:
    client_id: str
    client_secret: str


def fetch_access_token(public_api_root: str, creds: ClientCredentials) -> str:
    url = f"{public_api_root.rstrip('/')}/applications/token"
    payload = {
        "client_id": creds.client_id,
        "client_secret": creds.client_secret,
        "grant-type": "client_credentials",
    }
    response = requests.post(url, json=payload, timeout=30)
    if not response.ok:
        body = (response.text or "")[:500]
        raise AuthError(
            f"Access token request failed: {response.status_code} {response.reason} "
            f"(body: {body})"
        )
    data = response.json() or {}
    token = data.get("access_token")
    if not token:
        raise AuthError("Token response did not include 'access_token'.")
    return token
