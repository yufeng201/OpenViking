from types import SimpleNamespace

import httpx
import pytest
from fastapi import FastAPI

from openviking.server.auth import get_request_context
from openviking.server.routers import projects
from openviking.server.workspace_context import resolve_workspace_context
from openviking_cli.exceptions import FailedPreconditionError, InvalidArgumentError, NotFoundError
from tests.unit.projects.test_project_service import create, ctx


@pytest.mark.asyncio
async def test_capabilities_and_member_list_through_http(setup, monkeypatch):
    _, service = setup
    await create(service)
    app = FastAPI()
    app.state.config = SimpleNamespace(workspace_capture_enabled=True)
    app.include_router(projects.router)
    app.dependency_overrides[get_request_context] = lambda: ctx("bob")
    monkeypatch.setattr(projects, "project_service", lambda request: service)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        result = (await client.get("/api/v1/projects")).json()["result"]
        assert [p["project_id"] for p in result] == ["orders"]
        capability = (await client.get("/api/v1/workspace")).json()["result"]["capabilities"]
        assert capability["protocol_version"] == 2
        assert capability["project_capture"]
        app.state.config.workspace_capture_enabled = False
        assert (await client.get("/api/v1/workspace")).json()["result"]["capabilities"][
            "protocol_version"
        ] == 1


@pytest.mark.asyncio
async def test_header_resolution_validates_membership_and_fails_closed(setup, monkeypatch):
    storage, service = setup
    await create(service)
    monkeypatch.setattr(
        "openviking.server.dependencies.get_service",
        lambda: SimpleNamespace(viking_fs=SimpleNamespace(_async_agfs=storage)),
    )
    request = SimpleNamespace(
        headers={"X-OpenViking-Project": "orders"},
        app=SimpleNamespace(
            state=SimpleNamespace(config=SimpleNamespace(workspace_capture_enabled=True))
        ),
    )
    resolved = await resolve_workspace_context(request, ctx("bob"))
    assert resolved.workspace_target.owner_id == "orders"
    assert resolved.user.user_id == "bob"
    with pytest.raises(NotFoundError):
        await resolve_workspace_context(request, ctx("outsider"))
    request.headers["X-OpenViking-Workspace-Peer"] = "repo"
    with pytest.raises(InvalidArgumentError):
        await resolve_workspace_context(request, ctx())
    del request.headers["X-OpenViking-Workspace-Peer"]
    request.app.state.config.workspace_capture_enabled = False
    with pytest.raises(FailedPreconditionError):
        await resolve_workspace_context(request, ctx())


@pytest.mark.asyncio
@pytest.mark.parametrize("kind", [None, "peer", "project"])
async def test_session_create_does_not_initialize_personal_roots_for_workspace(kind, monkeypatch):
    from dataclasses import replace
    from unittest.mock import AsyncMock

    from openviking.core.workspace import WorkspaceTarget
    from openviking.server.auth import get_session_request_context
    from openviking.server.routers import sessions

    actor = ctx()
    if kind:
        target = WorkspaceTarget(
            kind, "orders" if kind == "project" else "alice", "repo" if kind == "peer" else None
        )
        actor = replace(actor, workspace_target=target)
    session = SimpleNamespace(session_id="route-test", uri="viking://test", user=actor.user)
    service = SimpleNamespace(
        initialize_user_directories=AsyncMock(),
        sessions=SimpleNamespace(
            create=AsyncMock(return_value=session),
            effective_auto_commit_policy=lambda value: {},
            effective_memory_extraction_config=lambda value: {},
        ),
    )
    monkeypatch.setattr(sessions, "get_service", lambda: service)
    app = FastAPI()
    app.include_router(sessions.router)
    app.dependency_overrides[get_session_request_context] = lambda: actor
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.post("/api/v1/sessions", json={"session_id": "route-test"})
    assert response.status_code == 200, response.text
    assert service.initialize_user_directories.await_count == (0 if kind else 1)
    service.sessions.create.assert_awaited_once()
