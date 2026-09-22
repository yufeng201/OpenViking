"""Account project administration and workspace capability discovery."""

from typing import Literal

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, ConfigDict, Field

from openviking.server.auth import get_request_context
from openviking.server.dependencies import get_service
from openviking.server.identity import RequestContext
from openviking.server.models import Response
from openviking.server.project_store import ProjectStore
from openviking.service.project_service import ProjectService

router = APIRouter(prefix="/api/v1", tags=["projects"])


class Repository(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str = Field(min_length=1, max_length=256)
    name: str = Field(default="", max_length=256)
    description: str = Field(default="", max_length=4096)


class CreateProject(BaseModel):
    model_config = ConfigDict(extra="forbid")
    project_id: str = Field(min_length=1, max_length=128)
    group_id: str = Field(min_length=1, max_length=128)
    name: str = Field(min_length=1, max_length=256)
    description: str = Field(default="", max_length=16384)
    repositories: list[Repository] = Field(default_factory=list, max_length=100)


class UpdateProject(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str | None = Field(default=None, min_length=1, max_length=256)
    description: str | None = Field(default=None, max_length=16384)
    repositories: list[Repository] | None = Field(default=None, max_length=100)
    status: Literal["active", "archived"] | None = None


def project_service(request: Request):
    return ProjectService(
        ProjectStore(get_service().viking_fs._async_agfs),
        getattr(request.app.state, "api_key_manager", None),
    )


@router.post("/projects")
async def create_project(
    body: CreateProject, request: Request, ctx: RequestContext = Depends(get_request_context)
):
    return Response(
        status="ok", result=await project_service(request).create(ctx, body.model_dump())
    )


@router.get("/projects")
async def list_projects(request: Request, ctx: RequestContext = Depends(get_request_context)):
    return Response(status="ok", result=await project_service(request).list(ctx))


@router.get("/projects/{project_id}")
async def get_project(
    project_id: str, request: Request, ctx: RequestContext = Depends(get_request_context)
):
    return Response(status="ok", result=await project_service(request).get(ctx, project_id))


@router.patch("/projects/{project_id}")
async def update_project(
    project_id: str,
    body: UpdateProject,
    request: Request,
    ctx: RequestContext = Depends(get_request_context),
):
    service = project_service(request)
    return Response(
        status="ok",
        result=await service.update(
            ctx, project_id, body.model_dump(exclude_unset=True, exclude_none=True)
        ),
    )


@router.get("/projects/{project_id}/members")
async def get_members(
    project_id: str, request: Request, ctx: RequestContext = Depends(get_request_context)
):
    service = project_service(request)
    service.require_admin(ctx)
    project = await service.get(ctx, project_id)
    return Response(
        status="ok", result=await service.store.members(ctx.account_id, project["group_id"])
    )


@router.put("/projects/{project_id}/members/{user_id}")
async def add_member(
    project_id: str,
    user_id: str,
    request: Request,
    ctx: RequestContext = Depends(get_request_context),
):
    return Response(
        status="ok", result=await project_service(request).change_member(ctx, project_id, user_id)
    )


@router.delete("/projects/{project_id}/members/{user_id}")
async def remove_member(
    project_id: str,
    user_id: str,
    request: Request,
    ctx: RequestContext = Depends(get_request_context),
):
    return Response(
        status="ok",
        result=await project_service(request).change_member(ctx, project_id, user_id, remove=True),
    )


@router.get("/workspace")
async def get_workspace(request: Request, ctx: RequestContext = Depends(get_request_context)):
    enabled = bool(getattr(request.app.state.config, "workspace_capture_enabled", False))
    return Response(
        status="ok",
        result={
            "target": ctx.workspace_target.to_dict() if ctx.workspace_target else None,
            "account_id": ctx.account_id,
            "user_id": ctx.user.user_id,
            # Advertise only complete paths; clients must fail closed for others.
            "capabilities": {
                "protocol_version": 2 if enabled else 1,
                "target_kinds": ["user", "peer", "project"] if enabled else ["user"],
                "project_management": True,
                "project_capture": enabled,
            },
        },
    )
