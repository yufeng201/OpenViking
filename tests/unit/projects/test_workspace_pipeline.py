from unittest.mock import AsyncMock

import pytest

from openviking.core.context import Context
from openviking.core.workspace import WorkspaceTarget, task_owner_key
from openviking.server.identity import RequestContext, Role
from openviking.service.workspace_sessions import workspace_candidate, workspace_meta_paths
from openviking.session.memory.streaming_memory_updater import make_streaming_memory_updater_key
from openviking.session.memory.workspace_registry import PROJECT_MEMORY_TYPES, workspace_registry
from openviking.session.session import SessionMeta
from openviking.storage.queuefs.session_commit_msg import SessionCommitMsg
from openviking.storage.queuefs.session_commit_processor import SessionCommitProcessor
from openviking_cli.session.user_id import UserIdentifier


def ctx(actor="alice", project="orders"):
    return RequestContext(
        UserIdentifier("acme", actor),
        Role.USER,
        workspace_target=WorkspaceTarget("project", project),
    )


def message():
    return SessionCommitMsg(
        task_id="t",
        session_id="s",
        session_uri="viking://project/orders/sessions/s",
        archive_uri="viking://project/orders/sessions/s/history/001",
        user=ctx().user.to_dict(),
        protocol_version=2,
        workspace_target=ctx().workspace_target.to_dict(),
    )


def test_queue_restores_owner_without_replacing_actor():
    msg, restored = SessionCommitProcessor._parse_message(message().to_dict())
    assert restored.workspace_target == ctx().workspace_target
    assert restored.user.user_id == "alice"
    assert restored.workspace_worker
    assert task_owner_key(restored) == "~project~orders"
    assert task_owner_key(restored) == task_owner_key(ctx("bob"))


@pytest.mark.parametrize(
    "field,value",
    [
        ("session_uri", "viking://project/payments/sessions/s"),
        ("archive_uri", "viking://project/orders/sessions/s/history/../elsewhere"),
        ("protocol_version", 3),
        ("workspace_target", None),
    ],
)
def test_queue_rejects_mismatched_or_unknown_ownership(field, value):
    payload = message().to_dict()
    payload[field] = value
    with pytest.raises(ValueError):
        SessionCommitProcessor._parse_message(payload)


def test_metadata_and_scan_ownership_validation():
    meta = SessionMeta(
        session_id="s",
        created_by_account_id="acme",
        created_by_user_id="alice",
        workspace_target=ctx().workspace_target.to_dict(),
    )
    assert SessionMeta.from_dict(meta.to_dict()).workspace_target == meta.workspace_target
    path = "/local/acme/project/orders/sessions/s/.meta.json"
    assert workspace_candidate(path, meta.to_dict()) == (
        "s",
        "acme",
        "alice",
        ctx().workspace_target,
    )
    with pytest.raises(ValueError):
        workspace_candidate(path.replace("orders", "other"), meta.to_dict())


def test_project_schemas_are_bound_and_do_not_share_mutable_state():
    registry = workspace_registry(ctx())
    assert set(registry.list_names()) == PROJECT_MEMORY_TYPES
    other = workspace_registry(ctx(project="payments"))
    for schema in registry.list_all():
        assert schema.directory == f"viking://project/orders/memories/{schema.memory_type}"
        assert not schema.peer_enabled
        assert other.get(schema.memory_type).directory.startswith("viking://project/payments/")
    assert make_streaming_memory_updater_key(
        request_context=ctx()
    ) == make_streaming_memory_updater_key(request_context=ctx("bob"))
    assert make_streaming_memory_updater_key(
        request_context=ctx()
    ) != make_streaming_memory_updater_key(request_context=ctx(project="payments"))


def test_project_index_owner_is_not_contributor():
    record = Context(
        uri="viking://project/orders/resources/api", user=ctx().user, owner_user_id="alice"
    ).to_dict()
    assert record["owner_project_id"] == "orders"
    assert record["owner_user_id"] is None
    assert record["account_id"] == "acme"


@pytest.mark.asyncio
async def test_scan_project_and_peer_roots():
    tree = {
        "/local/acme/project": ["orders"],
        "/local/acme/user": ["alice"],
        "/local/acme/user/alice/peers": ["repo"],
        "/local/acme/project/orders/sessions": ["s"],
        "/local/acme/user/alice/peers/repo/sessions": ["s"],
    }
    agfs = AsyncMock()
    agfs.ls.side_effect = lambda path: [{"name": name, "isDir": True} for name in tree[path]]
    assert [p async for p in workspace_meta_paths(agfs, "acme")] == [
        "/local/acme/project/orders/sessions/s/.meta.json",
        "/local/acme/user/alice/peers/repo/sessions/s/.meta.json",
    ]
