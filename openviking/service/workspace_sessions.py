"""Workspace session discovery and metadata validation for background scans."""

from openviking.core.identifiers import validate_identifier_part
from openviking.core.workspace import WorkspaceTarget
from openviking.server.error_mapping import is_not_found_error


async def directories(agfs, path):
    try:
        entries = await agfs.ls(path)
    except Exception as exc:
        if is_not_found_error(exc):
            return []
        raise
    return [
        e["name"]
        for e in entries
        if e.get("isDir") and not validate_identifier_part(e.get("name"), "directory")
    ]


async def workspace_meta_paths(agfs, account_id):
    root = f"/local/{account_id}"
    roots = [
        f"{root}/project/{project}/sessions"
        for project in await directories(agfs, f"{root}/project")
    ]
    for user in await directories(agfs, f"{root}/user"):
        roots.extend(
            f"{root}/user/{user}/peers/{peer}/sessions"
            for peer in await directories(agfs, f"{root}/user/{user}/peers")
        )
    for session_root in roots:
        for session in await directories(agfs, session_root):
            yield f"{session_root}/{session}/.meta.json"


def workspace_candidate(meta_path, meta):
    value = meta.get("workspace_target")
    if not value:
        return None
    target = WorkspaceTarget.from_dict(value)
    parts = meta_path.strip("/").split("/")
    account = parts[1]
    session_id = meta.get("session_id")
    actor = meta.get("created_by_user_id")
    if validate_identifier_part(session_id, "session_id") or validate_identifier_part(
        actor, "user_id"
    ):
        raise ValueError("Workspace session has invalid identity")
    expected = (
        f"/local/{account}/{target.root.removeprefix('viking://')}/sessions/{session_id}/.meta.json"
    )
    if meta_path != expected or meta.get("created_by_account_id") != account:
        raise ValueError("Workspace metadata path mismatch")
    if target.kind != "project" and target.owner_id != actor:
        raise ValueError("Workspace session owner mismatch")
    return session_id, account, actor, target
