from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from openviking.session.memory.dataclass import (
    MemoryFile,
    MemoryOperationSource,
    ResolvedOperation,
    ResolvedOperations,
)
from openviking.session.memory.project_candidates import retain_project_candidates
from openviking.session.memory.project_provenance import add_project_source
from openviking.session.memory.streaming_memory_updater import (
    MemoryUpdateRequest,
    _inherit_source_metadata_to_merged_operations,
    attach_source_to_request_operations,
)
from tests.unit.projects.test_workspace_pipeline import ctx


def operation(status="confirmed"):
    return ResolvedOperation(
        memory_type="decisions",
        uris=["viking://project/orders/memories/decisions/api.md"],
        memory_fields={"content": "Use POST", "evidence_status": status},
    )


def request(actor, archive, op):
    return MemoryUpdateRequest(
        operations=ResolvedOperations(upsert_operations=[op], delete_file_contents=[], errors=[]),
        messages=[SimpleNamespace(id=actor + "-message")],
        ctx=ctx(actor),
        metadata={
            "archive_uri": archive,
            "session_id": actor,
            "extracted_at": "now",
            "source_extraction_id": actor,
        },
    )


def test_provenance_uses_server_messages_and_preserves_both_contributors():
    inputs = []
    for actor in ["alice", "bob"]:
        op = operation()
        op.source = MemoryOperationSource(contributor_id="forged")
        req = request(actor, f"viking://project/orders/sessions/{actor}/history/1", op)
        attach_source_to_request_operations(req)
        assert op.source.contributor_id == actor
        assert op.source.source_message_ids == [actor + "-message"]
        inputs.append(op)
    merged = operation()
    _inherit_source_metadata_to_merged_operations(inputs, [merged])
    metadata = {"owner_project_id": "forged"}
    add_project_source(metadata, merged, ctx())
    add_project_source(metadata, merged, ctx())
    assert metadata["owner_project_id"] == "orders"
    assert {x["contributor_id"] for x in metadata["sources"]} == {"alice", "bob"}
    assert len(metadata["sources"]) == 2
    with pytest.raises(ValueError):
        add_project_source({}, merged, ctx(project="other"))


@pytest.mark.asyncio
async def test_conflicts_and_deletes_are_archived_idempotently():
    raw = ""

    async def read(*args, **kwargs):
        return raw

    async def write(uri, content, **kwargs):
        nonlocal raw
        raw = content

    fs = SimpleNamespace(
        _uri_to_path=lambda uri, **kwargs: uri,
        _async_agfs=SimpleNamespace(
            pathlock_acquire_exact=AsyncMock(return_value={}), pathlock_release=AsyncMock()
        ),
        read_file=read,
        write_file=write,
    )
    for _ in range(2):
        operations = ResolvedOperations(
            upsert_operations=[operation(), operation("conflict")],
            delete_file_contents=[
                MemoryFile(uri="viking://project/orders/memories/decisions/old.md")
            ],
            errors=[],
        )
        await retain_project_candidates(
            operations,
            archive_uri="viking://project/orders/sessions/alice/history/1",
            messages=[SimpleNamespace(id="m")],
            ctx=ctx(),
            fs=fs,
        )
        assert len(operations.upsert_operations) == 1
        assert operations.delete_file_contents == []
    assert len(raw.splitlines()) == 2
    assert '"message_ids": ["m"]' in raw
