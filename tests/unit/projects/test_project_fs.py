from dataclasses import replace
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from openviking.core.workspace import WorkspaceTarget
from openviking.server.identity import Role
from openviking.storage.acl import AclAction
from openviking.storage.viking_fs import VikingFS
from openviking_cli.exceptions import ConflictError, PermissionDeniedError
from tests.unit.projects.test_project_service import create, ctx


@pytest.mark.asyncio
@pytest.mark.parametrize("acl_enabled", [False, True])
async def test_member_and_author_permissions_through_real_fs_gate(setup, acl_enabled):
    storage, service = setup
    await create(service)
    fs = VikingFS(agfs=SimpleNamespace())
    fs._async_agfs = storage
    fs.acl_manager = SimpleNamespace(is_enabled=AsyncMock(return_value=acl_enabled))
    alice = replace(
        ctx(), workspace_target=WorkspaceTarget("project", "orders"), project_ids=("orders",)
    )
    bob = replace(alice, user=ctx("bob").user)
    charlie = replace(alice, user=ctx("charlie").user)
    session_uri = "viking://project/orders/sessions/s"
    storage.files["/local/acme/project/orders/sessions/s/.meta.json"] = (
        b'{"created_by_user_id":"alice"}'
    )
    for member in (alice, bob):
        await fs._ensure_access(session_uri + "/messages.jsonl", member)
    with pytest.raises(PermissionDeniedError):
        await fs._ensure_access(session_uri, charlie)
    # A raw file endpoint never receives the internal session capability.
    with pytest.raises(PermissionDeniedError):
        await fs._ensure_access(session_uri + "/messages.jsonl", alice, action=AclAction.WRITE)
    await fs._ensure_access(
        session_uri + "/messages.jsonl",
        replace(alice, workspace_session_uri=session_uri),
        action=AclAction.WRITE,
    )
    with pytest.raises(PermissionDeniedError):
        await fs._ensure_access(
            session_uri + "/messages.jsonl",
            replace(bob, workspace_session_uri=session_uri),
            action=AclAction.WRITE,
        )
    with pytest.raises(PermissionDeniedError):
        await fs._ensure_access(
            session_uri + "/messages.jsonl",
            replace(bob, role=Role.ADMIN, workspace_session_uri=session_uri),
            action=AclAction.WRITE,
        )
    with pytest.raises(PermissionDeniedError):
        await fs._ensure_access(
            "viking://project/orders/resources/api", alice, action=AclAction.MANAGE
        )
    await fs._ensure_access("viking://project/orders/resources/api", alice, action=AclAction.WRITE)


@pytest.mark.asyncio
async def test_accepted_worker_survives_member_removal_but_not_archive(setup):
    storage, service = setup
    await create(service)
    worker = replace(
        ctx(),
        workspace_target=WorkspaceTarget("project", "orders"),
        project_ids=("orders",),
        workspace_worker=True,
        workspace_session_uri="viking://project/orders/sessions/s",
    )
    storage.files["/local/acme/_system/groups.json"] = b'{"groups":{"team":{"members":[]}}}'
    fs = VikingFS(agfs=SimpleNamespace())
    fs._async_agfs = storage
    uri = "viking://project/orders/memories/conventions/api.md"
    await fs._ensure_access(uri, worker, action=AclAction.WRITE)
    with pytest.raises(PermissionDeniedError):
        await fs._ensure_access("viking://user/alice/memories/a.md", worker, action=AclAction.WRITE)
    await service.update(ctx(role=Role.ADMIN), "orders", {"status": "archived"})
    with pytest.raises(ConflictError, match="archived"):
        await fs._ensure_access(uri, worker, action=AclAction.WRITE)
