import asyncio
import json
from unittest.mock import AsyncMock

import pytest

from openviking.pyagfs.exceptions import AGFSNotFoundError
from openviking.server.identity import RequestContext, Role
from openviking.server.project_store import ProjectStore
from openviking.service.project_service import ProjectService
from openviking.storage.acl import AclAction
from openviking.storage.workspace_access import project_access
from openviking_cli.exceptions import FailedPreconditionError, NotFoundError, PermissionDeniedError
from openviking_cli.session.user_id import UserIdentifier


class Storage:
    def __init__(self):
        self.files = {}
        self.locks = {}
        self.fail_overview = False

    async def read(self, path):
        if path not in self.files:
            raise AGFSNotFoundError("missing")
        return self.files[path]

    async def write(self, path, data):
        if path.endswith("overview.md") and self.fail_overview:
            raise OSError("storage unavailable")
        self.files[path] = data

    async def ensure_parent_dirs(self, path):
        pass

    async def ls(self, root):
        return [
            {"name": p[len(root) + 1 :], "isDir": False}
            for p in self.files
            if p.startswith(root + "/") and "/" not in p[len(root) + 1 :]
        ]

    async def pathlock_acquire_exact(self, path, **kwargs):
        lock = self.locks.setdefault(path, asyncio.Lock())
        await lock.acquire()
        return lock

    async def pathlock_release(self, lock):
        lock.release()


def ctx(user="alice", role=Role.USER, account="acme"):
    return RequestContext(UserIdentifier(account, user), role)


@pytest.fixture
def setup():
    storage = Storage()
    storage.files["/local/acme/_system/groups.json"] = json.dumps(
        {"groups": {"team": {"members": ["alice", "bob"]}}}
    ).encode()
    service = ProjectService(ProjectStore(storage), AsyncMock())
    return storage, service


async def create(service):
    return await service.create(
        ctx(role=Role.ADMIN),
        {
            "project_id": "orders",
            "group_id": "team",
            "name": "Orders",
            "description": "Company order service",
            "repositories": [],
        },
    )


@pytest.mark.asyncio
async def test_members_share_assets_and_removal_is_authoritative(setup):
    storage, service = setup
    await create(service)
    assert (await service.get(ctx("bob"), "orders"))["name"] == "Orders"
    with pytest.raises(NotFoundError):
        await service.get(ctx("charlie"), "orders")
    with pytest.raises(NotFoundError):
        await service.get(ctx(account="elsewhere"), "orders")
    storage.files["/local/acme/_system/groups.json"] = json.dumps(
        {"groups": {"team": {"members": ["bob"]}}}
    ).encode()
    with pytest.raises(NotFoundError):
        await service.get(ctx(), "orders")
    assert len(await service.list(ctx("bob"))) == 1
    assert await service.list(ctx()) == []
    assert (
        "Company order service"
        in storage.files["/local/acme/project/orders/memories/overview.md"].decode()
    )


@pytest.mark.asyncio
async def test_failed_initialization_can_retry_without_becoming_visible(setup):
    storage, service = setup
    storage.fail_overview = True
    with pytest.raises(OSError):
        await create(service)
    with pytest.raises(NotFoundError):
        await service.get(ctx(), "orders")
    storage.fail_overview = False
    assert (await create(service))["initialized"]


@pytest.mark.asyncio
async def test_management_and_group_deletion_guards(setup):
    _, service = setup
    await create(service)
    with pytest.raises(PermissionDeniedError):
        await service.update(ctx(), "orders", {"name": "Hijack"})
    with pytest.raises(FailedPreconditionError):
        await service.ensure_group_unreferenced("acme", "team")
    await service.change_member(ctx(role=Role.ADMIN), "orders", "bob", remove=True)
    service.manager.remove_group_member.assert_awaited_once_with("acme", "team", "bob")
    assert (await service.get(ctx(), "orders"))["name"] == "Orders"


@pytest.mark.asyncio
async def test_project_fs_checks_do_not_depend_on_acl_or_context_cache(setup):
    storage, service = setup
    await create(service)
    uri = "viking://project/orders/memories/overview.md"
    assert await project_access(storage, uri, ctx("bob"), AclAction.READ)
    assert not await project_access(storage, uri, ctx("charlie"), AclAction.READ)
    assert not await project_access(storage, uri, ctx(), AclAction.WRITE)
    assert not await project_access(
        storage, "viking://project/fake", ctx(role=Role.ROOT), AclAction.READ
    )
