"""Resolve an authenticated workspace without accepting ownership from clients."""

from dataclasses import replace

from openviking.core.workspace import WorkspaceTarget
from openviking.server.project_store import ProjectStore
from openviking.service.project_service import ProjectService
from openviking_cli.exceptions import FailedPreconditionError, InvalidArgumentError


async def resolve_workspace_context(request, ctx):
    headers = request.headers
    project = headers.get("X-OpenViking-Project")
    peer = headers.get("X-OpenViking-Workspace-Peer")
    try:
        target = WorkspaceTarget.from_headers(ctx.user.user_id, project, peer)
    except ValueError as exc:
        raise InvalidArgumentError(str(exc)) from exc
    if target is None:
        return ctx
    if ctx.actor_peer_id and (target.kind == "project" or ctx.actor_peer_id != target.peer_id):
        raise InvalidArgumentError("Actor peer conflicts with workspace target")
    config = getattr(request.app.state, "config", None)
    if not getattr(config, "workspace_capture_enabled", False):
        raise FailedPreconditionError("Workspace capture is not enabled on this server")
    resolved = replace(ctx, workspace_target=target, actor_peer_id=None)
    if target.kind == "project":
        from openviking.server.dependencies import get_service

        service = ProjectService(
            ProjectStore(get_service().viking_fs._async_agfs),
            getattr(request.app.state, "api_key_manager", None),
        )
        await service.get(ctx, target.owner_id)
        resolved.project_ids = (target.owner_id,)
    return resolved
