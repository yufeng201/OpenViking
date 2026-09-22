import json
from dataclasses import replace
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from openviking.core.workspace import WorkspaceTarget
from openviking.server.project_store import ProjectStore
from openviking.server.routers import session_repository
from openviking.service.project_service import ProjectService
from openviking.session.memory.repository_context import apply_repository_context
from openviking.session.memory.workspace_registry import workspace_registry
from openviking.session.session import Session, SessionMeta
from openviking.storage.viking_fs import VikingFS
from openviking.utils.agfs_utils import RagfsBindingConfig, create_agfs_client
from openviking_cli.exceptions import ConflictError, InvalidArgumentError, PermissionDeniedError
from openviking_cli.utils.config.agfs_config import AGFSConfig
from tests.unit.projects.test_project_service import create, ctx


@pytest.mark.asyncio
async def test_repository_binding_persists_and_cannot_change(tmp_path, monkeypatch):
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
    projects = ProjectService(store, None)
    await create(projects)
    await projects.update(
        replace(ctx(), role="admin"),
        "orders",
        {"repositories": [{"id": "api", "name": "API"}, {"id": "ui", "name": "UI"}]},
    )
    actor = replace(
        ctx(), workspace_target=WorkspaceTarget("project", "orders"), project_ids=("orders",)
    )
    session = Session(fs, ctx=actor, session_id="repository-test")
    await session.ensure_exists()
    service = SimpleNamespace(
        sessions=SimpleNamespace(_viking_fs=fs, get=AsyncMock(return_value=session))
    )
    monkeypatch.setattr(session_repository, "get_service", lambda: service)
    bind = session_repository.RepositoryBinding
    await session_repository.bind_repository(
        session.session_id, bind(repository_id="api", title="Order API"), actor
    )
    await session_repository.bind_repository(
        session.session_id, bind(repository_id="api", title="Do not overwrite"), actor
    )
    reader = Session(fs, ctx=actor, session_id=session.session_id)
    await reader.load()
    assert reader.meta.repository == {"id": "api", "name": "API"}
    assert reader.meta.title == "Order API"
    assert reader.uri == "viking://project/orders/sessions/repository-test"
    with pytest.raises(ConflictError):
        await session_repository.bind_repository(
            session.session_id, bind(repository_id="ui"), actor
        )
    with pytest.raises(InvalidArgumentError):
        await session_repository.bind_repository(
            session.session_id, bind(repository_id="missing"), actor
        )
    bob = replace(actor, user=ctx("bob").user)
    with pytest.raises(PermissionDeniedError):
        await session_repository.bind_repository(session.session_id, bind(repository_id="api"), bob)
    registry = workspace_registry(actor)
    repository = await apply_repository_context(fs, actor, session.session_id, registry)
    assert repository["id"] == "api"
    assert all("Session source repository" in s.description for s in registry.list_all())
    assert all(
        "Session source repository" not in s.description
        for s in workspace_registry(actor).list_all()
    )
    await projects.update(replace(ctx(), role="admin"), "orders", {"status": "archived"})
    with pytest.raises(ConflictError):
        await session_repository.bind_repository(
            session.session_id, bind(repository_id="api"), actor
        )


def test_legacy_metadata_has_no_repository():
    meta = SessionMeta.from_dict({"session_id": "old"})
    assert meta.repository is None
    assert meta.title == ""
    assert SessionMeta.from_dict(meta.to_dict()).repository is None
