"""Immutable per-client workspace selection."""

import re


def workspace_headers(project_id=None, peer_id=None):
    if project_id is not None and peer_id is not None:
        raise ValueError("project_id and workspace_peer_id are mutually exclusive")
    result = {}
    for name, value in (
        ("X-OpenViking-Project", project_id),
        ("X-OpenViking-Workspace-Peer", peer_id),
    ):
        if value is None:
            continue
        if (
            not isinstance(value, str)
            or not re.fullmatch(r"[a-zA-Z0-9_.@-]{1,128}", value)
            or value in {".", ".."}
            or value.count("@") > 1
        ):
            raise ValueError("Invalid workspace identifier")
        result[name] = value
    return result
