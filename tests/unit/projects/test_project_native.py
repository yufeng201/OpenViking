"""Project storage/session integration against the native local AGFS binding."""

import json
from dataclasses import replace

import pytest

from openviking.core.workspace import WorkspaceTarget
from openviking.message.part import TextPart
from openviking.server.project_store import ProjectStore
from openviking.service.project_service import ProjectService
from openviking.session.session import Session
from openviking.storage.viking_fs import VikingFS
from openviking.utils.agfs_utils import RagfsBindingConfig, create_agfs_client
from openviking_cli.exceptions import PermissionDeniedError
from openviking_cli.utils.config.agfs_config import AGFSConfig
from tests.unit.projects.test_project_service import create, ctx


@pytest.mark.asyncio
async def test_native_project_session_retains_company_ownership(tmp_path, monkeypatch):
    fs = VikingFS(
        agfs=create_agfs_client(
            RagfsBindingConfig(agfs=AGFSConfig(path=str(tmp_path), backend="local"))
        )
    )
    store = ProjectStore(fs._async_agfs)
    path = "/local/acme/_system/groups.json"
    await fs._async_agfs.ensure_parent_dirs(path)
    await fs._async_agfs.write(
        path, json.dumps({"groups": {"team": {"members": ["alice", "bob"]}}}).encode()
    )
    service = ProjectService(store, None)
    await create(service)
    alice = replace(
        ctx(), workspace_target=WorkspaceTarget("project", "orders"), project_ids=("orders",)
    )
    bob = replace(alice, user=ctx("bob").user)
    session = Session(fs, ctx=alice, session_id="server-code")
    await session.ensure_exists()
    await session.add_message_async("user", [TextPart(text="The API is POST /orders")])
    reader = Session(fs, ctx=bob, session_id="server-code")
    await reader.load()
    uri = "viking://project/orders/sessions/server-code/messages.jsonl"
    assert "POST /orders" in await fs.read_file(uri, ctx=bob)
    with pytest.raises(PermissionDeniedError):
        await reader.add_message_async("user", [TextPart(text="overwrite")])
    from types import SimpleNamespace
    from unittest.mock import AsyncMock

    from openviking.server.user_config import effective_resource_add_target
    from openviking.service.task_store import PersistentTaskStore
    from openviking.service.task_tracker import TaskTracker
    from openviking.storage.queuefs.session_commit_processor import SessionCommitProcessor

    assert (
        await effective_resource_add_target(viking_fs=fs, ctx=alice, server_config=None)
        == "viking://project/orders/resources"
    )
    queue = SimpleNamespace(enqueue=AsyncMock())
    tracker = TaskTracker(store=PersistentTaskStore(fs._async_agfs))
    monkeypatch.setattr("openviking.storage.queuefs.get_queue_manager", lambda: queue)
    monkeypatch.setattr("openviking.service.task_tracker.get_task_tracker", lambda: tracker)
    result = await session.commit_async()
    assert result["archived"]
    payload = queue.enqueue.call_args.args[1]
    _, worker = SessionCommitProcessor._parse_message(payload)
    assert worker.workspace_target == alice.workspace_target
    assert await tracker.get(result["task_id"], account_id="acme", user_id="~project~orders")
    archived_uri = payload["archive_uri"] + "/messages.jsonl"
    assert "POST /orders" in await fs.read_file(archived_uri, ctx=bob)
    uri = archived_uri

    await fs._async_agfs.write(path, b'{"groups":{"team":{"members":["bob"]}}}')
    assert "POST /orders" in await fs.read_file(uri, ctx=bob)
    with pytest.raises(PermissionDeniedError):
        await fs.read_file(uri, ctx=alice)
    # The accepted commit can persist derived knowledge after its author leaves.
    from openviking.session.memory.dataclass import MemoryOperationSource, ResolvedOperation
    from openviking.session.memory.memory_updater import MemoryUpdater
    from openviking.session.memory.utils.memory_file_utils import MemoryFileUtils
    from openviking.session.memory.workspace_registry import workspace_registry

    updater = MemoryUpdater(registry=workspace_registry(worker))
    updater._viking_fs = fs
    memory_uri = "viking://project/orders/memories/decisions/orders-api.md"
    operation = ResolvedOperation(
        memory_type="decisions",
        uris=[memory_uri],
        memory_fields={
            "name": "orders-api",
            "content": "The confirmed API is POST /orders",
            "evidence_status": "confirmed",
        },
        project_sources=[
            MemoryOperationSource(
                extraction_id="native-test",
                archive_uri=payload["archive_uri"],
                session_id="server-code",
                contributor_id="alice",
                source_message_ids=["source-message"],
            )
        ],
    )
    await updater._apply_upsert(operation, worker)
    memory = MemoryFileUtils.read(await fs.read_file(memory_uri, ctx=bob), uri=memory_uri)
    assert memory.extra_fields["owner_project_id"] == "orders"
    assert memory.extra_fields["sources"][0]["contributor_id"] == "alice"
    assert "POST /orders" in memory.content

    # Removing a session is an admin capability, separate from author-only append.
    from openviking.server.identity import Role

    admin = replace(bob, role=Role.ADMIN)
    with pytest.raises(PermissionDeniedError):
        await fs.rm(session.uri, recursive=True, ctx=bob)
    admin_reader = Session(fs, ctx=admin, session_id="server-code")
    await admin_reader.load()
    with pytest.raises(PermissionDeniedError):
        await admin_reader.add_message_async("user", [TextPart(text="impersonate")])
    project = await store.get("acme", "orders")
    project["status"] = "archived"
    await store.save("acme", project)
    with pytest.raises(PermissionDeniedError):
        await fs.rm(session.uri, recursive=True, ctx=admin)
    project["status"] = "active"
    await store.save("acme", project)
    await fs.rm(session.uri, recursive=True, ctx=admin)
    assert not await admin_reader.exists()
