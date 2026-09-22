"""Asset ownership survives QueueFS ACK and restart without changing the actor."""

import pytest

from openviking.service.task_store import PersistentTaskStore
from openviking.service.task_tracker import TaskStatus, TaskTracker
from openviking.service.task_work_index import (
    TaskWorkIndex,
    bind_task_context,
    extract_task_metadata,
    prepare_task_payload,
)
from tests.test_task_tracker import _FakeAgfs


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "root,owner",
    [
        ("viking://project/orders", "~project~orders"),
        ("viking://user/alice/peers/repo", "~peer~alice~repo"),
    ],
)
@pytest.mark.parametrize("failed", [False, True])
@pytest.mark.parametrize("message_kind", ["resource", "session", "semantic"])
async def test_workspace_task_ack_and_restart(root, owner, failed, message_kind):
    store = PersistentTaskStore(_FakeAgfs())
    tracker = TaskTracker(store=store)
    task = await tracker.create("session_commit", account_id="acme", user_id=owner)
    if message_kind == "resource":
        raw = {
            "task_id": task.task_id,
            "account_id": "acme",
            "user_id": "alice",
            "root_uri": root + "/resources/doc",
        }
    else:
        raw = {
            "task_id": task.task_id,
            "user": {"account_id": "acme", "user_id": "alice"},
            "session_uri": root + "/sessions/s",
        }
    if message_kind == "semantic":
        raw = {
            "task_id": task.task_id,
            "account_id": "acme",
            "user_id": "alice",
            "uri": root + "/memories/experiences/entry.md",
        }
    payload, metadata = prepare_task_payload(raw)
    assert metadata.user_id == owner
    assert payload.get("user_id", payload.get("user", {}).get("user_id")) == "alice"
    assert extract_task_metadata({"data": payload}).user_id == owner
    # Messages already queued before this fix must be recoverable too.
    legacy = {k: v for k, v in payload.items() if k != "_task_owner_id"}
    assert extract_task_metadata(legacy).user_id == owner
    index = TaskWorkIndex()
    owners = index.rebuild({"queue": [payload]})
    restarted = TaskTracker(store=store)
    restarted.attach_work_index(index)
    assert len(await restarted.restore_work_tasks(owners)) == 1
    await restarted.start(task.task_id, account_id="acme", user_id=owner)
    if failed:
        await restarted.fail(task.task_id, "test failure", account_id="acme", user_id=owner)
    else:
        await restarted.complete(task.task_id, {"ok": True}, account_id="acme", user_id=owner)
    await index.prepare_ack("queue", payload)
    result = await restarted.get(task.task_id, account_id="acme", user_id=owner)
    assert result.status == (TaskStatus.FAILED if failed else TaskStatus.COMPLETED)


def test_descendant_work_inherits_task_owner_but_preserves_contributor():
    with bind_task_context("task", "acme", "~project~orders"):
        payload, metadata = prepare_task_payload({"user_id": "alice", "account_id": "acme"})
    assert payload["user_id"] == "alice"
    assert metadata.user_id == "~project~orders"
    assert extract_task_metadata(payload).user_id == "~project~orders"
