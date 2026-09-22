"""Workspace authorization independent of optional resource ACLs."""

from openviking.server.identity import Role
from openviking.server.project_store import ProjectStore
from openviking.storage.acl import AclAction
from openviking_cli.exceptions import NotFoundError


async def project_access(agfs, uri, ctx, action):
    parts = uri.removeprefix("viking://").strip("/").split("/")
    if not parts or parts[0] != "project":
        return None
    if len(parts) < 2:
        return False
    store = ProjectStore(agfs)
    try:
        project = await store.get(ctx.account_id, parts[1])
        if not project.get("initialized"):
            return False
        worker = (
            ctx.workspace_worker
            and ctx.workspace_target is not None
            and ctx.workspace_target.kind == "project"
            and ctx.workspace_target.owner_id == parts[1]
        )
        if not worker and ctx.role not in {Role.ADMIN, Role.ROOT}:
            members = await store.members(ctx.account_id, project["group_id"])
            if ctx.user.user_id not in members:
                return False
    except (NotFoundError, ValueError):
        return False
    if ctx.workspace_target and ctx.workspace_target.root != f"viking://project/{parts[1]}":
        return False
    if action == AclAction.READ:
        return True
    if ctx.workspace_target is None:
        return False
    if project["status"] != "active" or len(parts) < 3:
        return False
    if parts[2] == "skills":
        return False
    if action == AclAction.MANAGE:
        return ctx.role in {Role.ADMIN, Role.ROOT} and len(parts) > 3
    if parts[2] == "resources":
        return True
    if parts[2] == "memories":
        return worker or ctx.role in {Role.ADMIN, Role.ROOT}
    if parts[2] != "sessions" or not ctx.workspace_session_uri:
        return False
    session_uri = ctx.workspace_session_uri
    if uri != session_uri and not uri.startswith(session_uri + "/"):
        return False
    if worker:
        return True
    meta_path = f"/local/{ctx.account_id}/" + session_uri.removeprefix("viking://") + "/.meta.json"
    meta = await store.read_json(meta_path)
    return meta is None or meta.get("created_by_user_id") == ctx.user.user_id
