"""Repository provenance for project sessions; storage URIs remain unchanged."""

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from openviking.server.auth import get_session_request_context
from openviking.server.dependencies import get_service
from openviking.server.identity import RequestContext
from openviking.server.models import Response
from openviking.server.project_store import ProjectStore
from openviking_cli.exceptions import InvalidArgumentError, PermissionDeniedError

router = APIRouter()


class RepositoryBinding(BaseModel):
    repository_id: str = Field(min_length=1, max_length=128, pattern=r"^[a-zA-Z0-9_.@-]+$")
    title: str = Field(default="", max_length=160)


@router.put("/{session_id}/repository")
async def bind_repository(
    session_id: str,
    body: RepositoryBinding,
    ctx: RequestContext = Depends(get_session_request_context),
):
    if not ctx.workspace_target or ctx.workspace_target.kind != "project":
        raise InvalidArgumentError("Repository binding requires a project workspace")
    service = get_service()
    fs = service.sessions._viking_fs
    project = await ProjectStore(fs._async_agfs).get(ctx.account_id, ctx.workspace_target.owner_id)
    repository = next(
        (r for r in project.get("repositories", []) if r["id"] == body.repository_id), None
    )
    if repository is None:
        raise InvalidArgumentError("Repository is not registered in this project")
    session = await service.sessions.get(session_id, ctx, auto_create=True)
    if session.meta.created_by_user_id != ctx.user.user_id:
        raise PermissionDeniedError("Only the session author can bind its repository")
    await session.update_config(
        repository={"id": repository["id"], "name": repository["name"] or repository["id"]}, title=body.title
    )
    return Response(
        status="ok",
        result={
            "session_id": session_id,
            "repository": session.meta.repository,
            "title": session.meta.title,
        },
    )
