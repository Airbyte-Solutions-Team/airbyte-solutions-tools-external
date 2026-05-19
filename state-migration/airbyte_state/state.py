"""State payload fetch, validation, and rewrite logic."""

from __future__ import annotations

import copy
from typing import Any, Dict


VALID_STATE_TYPES = {"stream", "global", "legacy", "not_set"}


class StateValidationError(RuntimeError):
    pass


def validate_state_response(connection_name: str, payload: Dict[str, Any]) -> str:
    """Validate the shape of a /v1/state/get response and return its stateType."""
    state_type = payload.get("stateType")
    if state_type not in VALID_STATE_TYPES:
        raise StateValidationError(
            f"Connection {connection_name!r}: invalid stateType {state_type!r} "
            f"(expected one of {sorted(VALID_STATE_TYPES)})"
        )

    if state_type == "stream":
        stream_state = payload.get("streamState")
        if not isinstance(stream_state, list):
            raise StateValidationError(
                f"Connection {connection_name!r}: stateType=stream requires a 'streamState' list"
            )
        for i, entry in enumerate(stream_state):
            descriptor = (entry or {}).get("streamDescriptor") or {}
            if not descriptor.get("name"):
                raise StateValidationError(
                    f"Connection {connection_name!r}: streamState[{i}] missing streamDescriptor.name"
                )

    elif state_type == "global":
        global_state = payload.get("globalState") or {}
        stream_states = global_state.get("streamStates")
        if not isinstance(stream_states, list):
            raise StateValidationError(
                f"Connection {connection_name!r}: stateType=global requires globalState.streamStates list"
            )

    return state_type


def build_target_payload(source_state: Dict[str, Any], target_connection_id: str) -> Dict[str, Any]:
    """Copy the source state response and rewrite only the top-level connectionId.

    Per the brief, stream-state payloads are preserved exactly; we never touch
    nested connector state. Only the connection-identifying field at the top
    of the payload is rewritten so the target connection accepts the write.
    """
    state_type = source_state.get("stateType")
    payload: Dict[str, Any] = {
        "connectionId": target_connection_id,
        "stateType": state_type,
    }

    if state_type == "legacy":
        payload["state"] = copy.deepcopy(source_state.get("state") or {})
    elif state_type == "stream":
        payload["streamState"] = copy.deepcopy(source_state.get("streamState") or [])
    elif state_type == "global":
        payload["globalState"] = copy.deepcopy(source_state.get("globalState") or {})
    elif state_type == "not_set":
        pass
    else:
        raise StateValidationError(f"Cannot build target payload for stateType={state_type!r}")

    return payload


def is_target_writable(existing_state: Dict[str, Any]) -> bool:
    """Return True if the target connection currently has no meaningful state."""
    state_type = existing_state.get("stateType")
    if state_type in (None, "not_set"):
        return True
    if state_type == "legacy" and not existing_state.get("state"):
        return True
    if state_type == "stream" and not existing_state.get("streamState"):
        return True
    if state_type == "global":
        global_state = existing_state.get("globalState") or {}
        if not global_state.get("streamStates") and not global_state.get("sharedState"):
            return True
    return False
